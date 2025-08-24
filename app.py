```python
import streamlit as st
import pandas as pd
import urllib.error
import plotly.graph_objects as go

# -----------------------------
# PASSWORD PROTECTION
# -----------------------------
def check_password():
    def password_entered():
        if st.session_state.get("password") == st.secrets["auth"]["password"]:
            st.session_state["auth_passed"] = True
        else:
            st.session_state["auth_passed"] = False

    if "auth_passed" not in st.session_state:
        st.text_input("Enter password and press Enter", type="password", on_change=password_entered, key="password")
        st.stop()
    elif not st.session_state["auth_passed"]:
        st.text_input("Enter password", type="password", on_change=password_entered, key="password")
        st.error("Incorrect password")
        st.stop()

check_password()

# -----------------------------
# LOAD DATA
# -----------------------------
@st.cache_data
def load_data():
    file_id = st.secrets["gdrive"]["file_id"]
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    try:
        df = pd.read_csv(url)
        return df
    except urllib.error.HTTPError:
        st.error("Could not load CSV file. Make sure it's shared publicly.")
        st.stop()
    except Exception as e:
        st.error(f"An unexpected error occurred: {e}")
        st.stop()

df = load_data()

# Ensure datetime column
if "yyyymmdd" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["yyyymmdd"]):
    df["yyyymmdd"] = pd.to_datetime(df["yyyymmdd"], errors="coerce")

# -----------------------------
# PLOTTING FUNCTIONS (Plotly)
# -----------------------------
def plot_monthly_exit_distribution_interactive(
    df,
    org_id,
    type="_abs",                # "_abs" (All animals) or "_cond" (Animals with an outcome)
    suffix="_zeros_replaced",   # "" (Raw) or "_zeros_replaced"
    title=None,
    smooth=False,
    window=3
):
    """
    Interactive stacked area plot of monthly exit probabilities using Plotly.
    Hover shows month/year and probability for each category.
    """
    org_data = df[df["organization_id"] == org_id].copy()
    if org_data.empty:
        raise ValueError("No data for this organization_id")
    org_name = org_data["organization_name"].iloc[0] if "organization_name" in org_data.columns else str(org_id)

    if not pd.api.types.is_datetime64_any_dtype(org_data["yyyymmdd"]):
        org_data["yyyymmdd"] = pd.to_datetime(org_data["yyyymmdd"], errors="coerce")

    metrics = {
        f"PAdopt_monthly{type}{suffix}": "Adopt",
        f"PReclaim_monthly{type}{suffix}": "Reclaim",
        f"PTransfer_monthly{type}{suffix}": "Transfer",
        f"PNonlive_monthly{type}{suffix}": "Non-live",
    }
    if type != "_cond":
        metrics[f"PNoExit_monthly{type}{suffix}"] = "No Exit"

    missing = [c for c in metrics.keys() if c not in org_data.columns]
    if missing:
        raise KeyError(f"Missing required columns: {missing}")

    plot_data = org_data[["yyyymmdd"] + list(metrics.keys())].copy().sort_values("yyyymmdd")
    plot_data = plot_data.set_index("yyyymmdd")
    plot_data.columns = [metrics[c] for c in plot_data.columns]

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

    # Add in a stable legend order
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
                    f"<b>{col}:</b> %{y:.1%}<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        title=title or f"Monthly Exit Probabilities for {org_name}",
        xaxis_title="Month",
        yaxis_title="Probability",
        yaxis=dict(tickformat=".0%", range=[0, 1]),
        hovermode="x unified",
        legend=dict(title="Outcome"),
        margin=dict(l=40, r=20, t=60, b=40),
    )
    return fig


def plot_inventory_interactive(
    df,
    org_id,
    suffix="",                 # "" (Raw) or "_zeros_replaced"
    title=None,
    smooth=False,
    window=3
):
    """
    Interactive line chart of Average Daily Inventory (CInventAvg) with hover tooltips.
    """
    org_data = df[df["organization_id"] == org_id].copy()
    if org_data.empty:
        raise ValueError("No data for this organization_id")
    org_name = org_data["organization_name"].iloc[0] if "organization_name" in org_data.columns else str(org_id)

    if not pd.api.types.is_datetime64_any_dtype(org_data["yyyymmdd"]):
        org_data["yyyymmdd"] = pd.to_datetime(org_data["yyyymmdd"], errors="coerce")

    metric_col = f"CInventAvg{suffix}"  # expect CInventAvg or CInventAvg_zeros_replaced
    if metric_col not in org_data.columns:
        raise KeyError(f"Missing required column: {metric_col}")

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
        title=title or f"Average Daily Inventory for {org_name}",
        xaxis_title="Month",
        yaxis_title="Animals (count)",
        hovermode="x unified",
        margin=dict(l=40, r=20, t=60, b=40),
    )
    return fig

# -----------------------------
# USER INTERFACE
# -----------------------------
st.title("📊 Shelter Dashboard")

# Organization selection
selection_mode = st.radio("Choose organization selection method:", ["By Name", "By ID"])
org_name = None
org_id = None

if selection_mode == "By Name":
    org_names = df["organization_name"].dropna().unique()
    org_name = st.selectbox("Select Organization Name", sorted(org_names))
    if org_name:
        ids = df.loc[df["organization_name"] == org_name, "organization_id"].dropna().unique()
        if len(ids) == 0:
            st.warning("No organization_id found for that name.")
            st.stop()
        org_id = int(ids[0])
else:
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

# Data version
data_variant = st.selectbox("Choose data version", ["Raw", "Zeros Replaced"])
suffix = "" if data_variant == "Raw" else "_zeros_replaced"

# Smoothing
smooth_label = st.checkbox("Smoothed", value=False)
window = 3
if smooth_label:
    window = st.slider("Smoothing window (months)", min_value=2, max_value=12, value=3)

# Plot selection (users can choose any combination)
st.subheader("Choose plots to display")
show_inventory = st.checkbox("Average Daily Inventory", value=True)
show_conditional = st.checkbox("Animals with an outcome (conditional)", value=True)
show_absolute = st.checkbox("All animals (absolute)", value=True)

# Plot
if org_id is not None and st.button("Show Plot(s)"):
    try:
        if show_inventory:
            inv_title = f"Average Daily Inventory for {org_name} ({data_variant})"
            fig_inv = plot_inventory_interactive(
                df,
                org_id=org_id,
                suffix=suffix,
                title=inv_title,
                smooth=smooth_label,
                window=window
            )
            st.plotly_chart(fig_inv, use_container_width=True)

        if show_conditional:
            cond_title = f"Conditional (Animals with an outcome) Probabilities for {org_name} ({data_variant})"
            fig_cond = plot_monthly_exit_distribution_interactive(
                df,
                org_id=org_id,
                type="_cond",
                suffix=suffix,
                title=cond_title,
                smooth=smooth_label,
                window=window
            )
            st.plotly_chart(fig_cond, use_container_width=True)

        if show_absolute:
            abs_title = f"Absolute (All animals) Probabilities for {org_name} ({data_variant})"
            fig_abs = plot_monthly_exit_distribution_interactive(
                df,
                org_id=org_id,
                type="_abs",
                suffix=suffix,
                title=abs_title,
                smooth=smooth_label,
                window=window
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
```
