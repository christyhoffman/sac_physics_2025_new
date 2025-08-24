import io
import urllib.error
import urllib.request
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


# =============================
# PASSWORD PROTECTION
# =============================
def check_password():
    def password_entered():
        if st.session_state.get("password") == st.secrets["auth"]["password"]:
            st.session_state["auth_passed"] = True
        else:
            st.session_state["auth_passed"] = False

    if "auth_passed" not in st.session_state:
        st.text_input(
            "Enter password and press Enter",
            type="password",
            on_change=password_entered,
            key="password",
        )
        st.stop()
    elif not st.session_state["auth_passed"]:
        st.text_input(
            "Enter password",
            type="password",
            on_change=password_entered,
            key="password",
        )
        st.error("Incorrect password")
        st.stop()


check_password()


# =============================
# ROBUST CSV LOADER
# =============================
@st.cache_data(show_spinner=True)
def _read_csv_bytes(raw_bytes: bytes) -> pd.DataFrame:
    """
    Try multiple parsing strategies on raw bytes.
    Returns a DataFrame or raises the last exception.
    """
    # 1) Fast path: default C engine
    try:
        return pd.read_csv(io.BytesIO(raw_bytes))
    except Exception:
        pass

    # 2) Python engine with comma, skipping bad lines
    try:
        return pd.read_csv(
            io.BytesIO(raw_bytes),
            engine="python",
            sep=",",
            quotechar='"',
            escapechar="\\",
            on_bad_lines="skip",
        )
    except Exception:
        pass

    # 3) Python engine with autodetected delimiter, skipping bad lines
    try:
        return pd.read_csv(
            io.BytesIO(raw_bytes),
            engine="python",
            sep=None,
            on_bad_lines="skip",
        )
    except Exception:
        pass

    # 4) Try tab-separated
    try:
        return pd.read_csv(
            io.BytesIO(raw_bytes),
            engine="python",
            sep="\t",
            on_bad_lines="skip",
        )
    except Exception as e:
        raise e


@st.cache_data(show_spinner=True)
def load_data_from_drive() -> pd.DataFrame:
    """
    Download CSV bytes from Google Drive export URL and parse robustly.
    """
    file_id = st.secrets["gdrive"]["file_id"]
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    try:
        with urllib.request.urlopen(url) as resp:
            raw_bytes = resp.read()
        df = _read_csv_bytes(raw_bytes)
        return df
    except urllib.error.HTTPError:
        st.error("Could not load CSV file from Google Drive (HTTP error). Make sure it is shared publicly.")
        st.stop()
    except Exception as e:
        raise e


# Try Drive first; if it fails, allow manual upload
drive_error = None
try:
    df = load_data_from_drive()
except Exception as e:
    drive_error = str(e)
    df = None

if df is None:
    st.error(
        "Could not parse the Google Drive CSV cleanly.\n\n"
        f"Details: {drive_error}\n\n"
        "Please upload the CSV manually below. The app will try multiple parsing strategies."
    )
    uploaded = st.file_uploader("Upload CSV", type=["csv"])
    if not uploaded:
        st.stop()
    try:
        df = _read_csv_bytes(uploaded.read())
        st.success("File uploaded and parsed successfully.")
    except Exception as e:
        st.error(f"Still couldn't parse the CSV: {e}")
        st.stop()


# =============================
# BASIC CLEANUP
# =============================
# Ensure datetime
if "yyyymmdd" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["yyyymmdd"]):
    df["yyyymmdd"] = pd.to_datetime(df["yyyymmdd"], errors="coerce")

# Coerce org id to nullable int
if "organization_id" in df.columns:
    df["organization_id"] = pd.to_numeric(df["organization_id"], errors="coerce").astype("Int64")

# Fill org name missing with empty string to avoid UI issues
if "organization_name" in df.columns:
    df["organization_name"] = df["organization_name"].fillna("")


def assert_columns_present(data: pd.DataFrame, cols: list) -> None:
    missing = [c for c in cols if c not in data.columns]
    if missing:
        raise KeyError(f"Missing required columns: {missing}")


# =============================
# PLOTTING (PLOTLY)
# =============================
def plot_monthly_exit_distribution_interactive(
    data: pd.DataFrame,
    org_id: int,
    type: str = "_abs",               # "_abs" (All animals) or "_cond" (Animals with an outcome)
    suffix: str = "_zeros_replaced",  # fixed to zeros_replaced in the UI
    title: Optional[str] = None,
    smooth: bool = False,
    window: int = 3,
) -> go.Figure:
    org_data = data[data["organization_id"] == org_id].copy()
    if org_data.empty:
        raise ValueError("No data for this organization_id")

    org_name = org_data["organization_name"].iloc[0] if "organization_name" in org_data.columns else str(org_id)

    if not pd.api.types.is_datetime64_any_dtype(org_data["yyyymmdd"]):
        org_data["yyyymmdd"] = pd.to_datetime(org_data["yyyymmdd"], errors="coerce")

    # Define metric columns
    column_map = {
        f"PAdopt_monthly{type}{suffix}": "Adopt",
        f"PReclaim_monthly{type}{suffix}": "Reclaim",
        f"PTransfer_monthly{type}{suffix}": "Transfer",
        f"PNonlive_monthly{type}{suffix}": "Non-live",
    }
    if type != "_cond":
        column_map[f"PNoExit_monthly{type}{suffix}"] = "No Exit"

    assert_columns_present(org_data, list(column_map.keys()))

    plot_data = org_data[["yyyymmdd"] + list(column_map.keys())].copy().sort_values("yyyymmdd")
    plot_data = plot_data.set_index("yyyymmdd")
    plot_data.columns = [column_map[c] for c in plot_data.columns]

    if smooth:
        plot_data = plot_data.rolling(window=window, min_periods=1, center=True).mean()

    colors = {
        "Adopt": "#0072B2",
        "Reclaim": "#CC79A7",
        "Transfer": "#E69F00",
        "Non-live": "#009E73",
        "No Exit": "#F0E442",
    }

    fig = go.Figure()
    x_vals = plot_data.index

    # Build traces (avoid f-strings evaluating %{y})
    for col in ["Adopt", "Reclaim", "Transfer", "Non-live", "No Exit"]:
        if col not in plot_data.columns:
            continue
        fig.add_trace(
            go.Scatter(
                x=x_vals,
                y=plot_data[col],
                mode="lines",
                name=col,
                stackgroup="one",
                line=dict(width=0.5),
                fillcolor=colors.get(col, None),
                hovertemplate=(
                    "<b>Date:</b> %{x|%b %Y}<br>"
                    + "<b>" + col + ":</b> %{y:.1%}<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        title=title or f"Monthly Exit Probabilities for {org_name} (Zeros Replaced)",
        xaxis_title="Month",
        yaxis_title="Probability",
        yaxis=dict(tickformat=".0%", range=[0, 1]),
        hovermode="x unified",
        legend=dict(title="Outcome"),
        margin=dict(l=40, r=20, t=60, b=40),
    )
    return fig


def plot_inventory_interactive(
    data: pd.DataFrame,
    org_id: int,
    suffix: str = "_zeros_replaced",  # fixed to zeros_replaced by default
    title: Optional[str] = None,
    smooth: bool = False,
    window: int = 3,
) -> go.Figure:
    org_data = data[data["organization_id"] == org_id].copy()
    if org_data.empty:
        raise ValueError("No data for this organization_id")

    org_name = org_data["organization_name"].iloc[0] if "organization_name" in org_data.columns else str(org_id)

    if not pd.api.types.is_datetime64_any_dtype(org_data["yyyymmdd"]):
        org_data["yyyymmdd"] = pd.to_datetime(org_data["yyyymmdd"], errors="coerce")

    metric_col = f"CInventAvg{suffix}"
    # Graceful fallback if variant column is missing
    if metric_col not in org_data.columns:
        base = "CInventAvg"
        if base in org_data.columns:
            metric_col = base
            st.warning(f"Column '{f'CInventAvg{suffix}'}' not found. Falling back to '{base}'.")
        else:
            raise KeyError(f"Missing required column: {f'CInventAvg{suffix}'}")

    plot_data = org_data[["yyyymmdd", metric_col]].copy().sort_values("yyyymmdd").set_index("yyyymmdd")

    if smooth:
        plot_data[metric_col] = plot_data[metric_col].rolling(window=window, min_periods=1, center=True).mean()

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=plot_data.index,
            y=plot_data[metric_col],
            mode="lines+markers",
            name="Average Daily Inventory",
            hovertemplate="<b>Date:</b> %{x|%b %Y}<br><b>Inventory:</b> %{y:.0f}<extra></extra>",
        )
    )

    fig.update_layout(
        title=title or f"Average Daily Inventory for {org_name} (Zeros Replaced)",
        xaxis_title="Month",
        yaxis_title="Animals (count)",
        hovermode="x unified",
        margin=dict(l=40, r=20, t=60, b=40),
    )
    return fig


# =============================
# UI
# =============================
st.title("📊 Shelter Dashboard")

# Organization selection
selection_mode = st.radio("Choose organization selection method:", ["By Name", "By ID"])
org_name = None
org_id = None

if selection_mode == "By Name":
    assert_columns_present(df, ["organization_name", "organization_id"])
    org_names = df["organization_name"].dropna().unique()
    org_name = st.selectbox("Select Organization Name", sorted(org_names))
    if org_name:
        ids = df.loc[df["organization_name"] == org_name, "organization_id"].dropna().unique()
        if len(ids) == 0:
            st.warning("No organization_id found for that name.")
            st.stop()
        org_id = int(ids[0])
else:
    assert_columns_present(df, ["organization_id", "organization_name"])
    org_id_input = st.text_input("Enter Organization ID")
    if org_id_input:
        try:
            org_id = int(org_id_input)
            matches = df[df["organization_id"] == org_id]["organization_name"].dropna().unique()
            if len(matches) > 0:
                org_name = matches[0]
                st.success(f"Found organization: {org_name}")
            else:
                st.warning("No organization found for that ID.")
                st.stop()
        except ValueError:
            st.error("Please enter a valid numeric organization ID.")
            st.stop()
    else:
        st.info("Please enter an organization ID.")
        st.stop()

# Fixed to zeros_replaced everywhere
suffix = "_zeros_replaced"

# Smoothing
smooth_label = st.checkbox("Smoothed", value=False)
window = 3
if smooth_label:
    window = st.slider("Smoothing window (months)", min_value=2, max_value=12, value=3)

# Plot selection (any combination)
st.subheader("Choose plots to display")
show_inventory = st.checkbox("Average Daily Inventory", value=True)
show_conditional = st.checkbox("Animals with an outcome (conditional)", value=True)
show_absolute = st.checkbox("All animals (absolute)", value=True)

# Render
if org_id is not None and st.button("Show Plot(s)"):
    try:
        if show_inventory:
            inv_title = f"Average Daily Inventory for {org_name} (Zeros Replaced)"
            fig_inv = plot_inventory_interactive(
                df,
                org_id=org_id,
                suffix=suffix,
                title=inv_title,
                smooth=smooth_label,
                window=window,
            )
            st.plotly_chart(fig_inv, use_container_width=True)

        if show_conditional:
            cond_title = f"Conditional (Animals with an outcome) Probabilities for {org_name} (Zeros Replaced)"
            fig_cond = plot_monthly_exit_distribution_interactive(
                df,
                org_id=org_id,
                type="_cond",
                suffix=suffix,
                title=cond_title,
                smooth=smooth_label,
                window=window,
            )
            st.plotly_chart(fig_cond, use_container_width=True)

        if show_absolute:
            abs_title = f"Absolute (All animals) Probabilities for {org_name} (Zeros Replaced)"
            fig_abs = plot_monthly_exit_distribution_interactive(
                df,
                org_id=org_id,
                type="_abs",
                suffix=suffix,
                title=abs_title,
                smooth=smooth_label,
                window=window,
            )
            st.plotly_chart(fig_abs, use_container_width=True)

        if not any([show_inventory, show_conditional, show_absolute]):
            st.info("Select at least one plot to display.")
    except KeyError as e:
        st.error(f"Data is missing required columns for this view: {e}")
    except ValueError as e:
        st.error(str(e))
    except Exception as e:
        st.error(f"Unexpected error: {e}")
