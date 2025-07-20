import streamlit as st
import pandas as pd
import plotly.express as px
import urllib.error

# --- PASSWORD PROTECTION ---
def check_password():
    def password_entered():
        st.session_state["auth_passed"] = (
            st.session_state["password"] == st.secrets["auth"]["password"]
        )

    if "auth_passed" not in st.session_state:
        st.text_input(
            "Enter password and press Enter",
            type="password",
            on_change=password_entered,
            key="password"
        )
        st.stop()
    elif not st.session_state["auth_passed"]:
        st.text_input(
            "Enter password",
            type="password",
            on_change=password_entered,
            key="password"
        )
        st.error("Incorrect password")
        st.stop()

check_password()

# --- LOAD DATA ---
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

# --- METRIC LABELS & ORDER ---
metric_label_map = {
    'CInventAvg':                     'Average Daily Inventory',
    'DIntake':                        'Daily Intake',

    'PAdopt_monthly':                 'Monthly Prob. of Adoption (out of outcomes only)',
    'PAdopt_monthly_abs':             'Monthly Prob. of Adoption (absolute)',

    'PTransfer_monthly':              'Monthly Prob. of Transfer (out of outcomes only)',
    'PTransfer_monthly_abs':          'Monthly Prob. of Transfer (absolute)',

    'PNonlive_monthly':               'Monthly Prob. of Nonlive (out of outcomes only)',
    'PNonlive_monthly_abs':           'Monthly Prob. of Nonlive (absolute)',

    'LAggreg':                        'Length of Stay',
    'SaveR_monthly':                  'Monthly Save Rate'
}
label_to_metric = {v: k for k, v in metric_label_map.items()}

ordered_labels = [
    'Average Daily Inventory',
    'Daily Intake',

    'Monthly Prob. of Adoption (out of outcomes only)',
    'Monthly Prob. of Adoption (absolute)',

    'Monthly Prob. of Transfer (out of outcomes only)',
    'Monthly Prob. of Transfer (absolute)',

    'Monthly Prob. of Nonlive (out of outcomes only)',
    'Monthly Prob. of Nonlive (absolute)',

    'Length of Stay',
    'Monthly Save Rate'
]

# --- PLOT FUNCTION WITH PLOTLY ---
def plot_organization_metrics_plotly(
    df, org_name, metrics, data_variant,
    smoothing_method, ema_span, sma_window
):
    org_data = df[df['organization_name'] == org_name].sort_values('yyyymmdd')
    if org_data.empty:
        st.warning(f"No data found for organization: {org_name}")
        return []

    plots = []
    # define which metrics are raw-counts vs percentages
    count_metrics = {'CInventAvg', 'DIntake'}
    for metric in metrics:
        if metric not in org_data.columns:
            st.warning(f"Metric {metric} not found in data.")
            continue

        # classify
        is_los    = metric.startswith("LAggreg")
        is_count  = metric in count_metrics
        is_abs    = metric.endswith("_abs")
        is_rate   = metric.startswith("P") and not is_los

        # extract & smooth
        y = org_data[metric]
        if smoothing_method == "Exponential Moving Average":
            y = y.ewm(span=ema_span, adjust=False).mean()
        elif smoothing_method == "Simple Moving Average":
            y = y.rolling(window=sma_window, min_periods=1).mean()

        # only convert raw‐prop to percent
        if is_rate and not is_abs:
            y = y * 100

        # axis labels & hover formatting
        if is_los:
            y_label, hover_fmt = "Days", "%{y:.2f}"
        elif is_count:
            y_label, hover_fmt = "Count", "%{y:.0f}"
        else:
            # either P*_abs or P*_monthly→percent
            y_label, hover_fmt = "Percentage", "%{y:.2f}%"

        # assemble DataFrame for Plotly
        plot_df = org_data.assign(y_val=y.round(2))

        fig = px.line(
            plot_df,
            x='yyyymmdd',
            y='y_val',
            markers=True,
            title=(
                f"{metric_label_map[metric.replace('_zeros_replaced','')]}"
                + (" (Zeros Replaced)" if data_variant=='Zeros Replaced' else "")
                + f" for {org_name}"
            ),
            labels={'yyyymmdd': 'Date', 'y_val': y_label},
            hover_data={'yyyymmdd': False, 'y_val': False}
        )

        fig.update_traces(
            hovertemplate=f"<b>Date:</b> %{{x}}<br><b>{y_label}:</b> {hover_fmt}<extra></extra>"
        )

        # only cap percent axes
        if not (is_los or is_count):
            fig.update_yaxes(range=[0, 100], ticksuffix="%")

        plots.append(fig)

    return plots

# --- USER INTERFACE ---
st.title("📊 Shelter Metrics Dashboard")

# Organization selection
selection_mode = st.radio(
    "Choose organization selection method:",
    ["By Name", "By ID"]
)
org_name = None

if selection_mode == "By Name":
    org_names = df['organization_name'].dropna().unique()
    org_name = st.selectbox("Select Organization Name", sorted(org_names))
else:
    org_id_input = st.text_input("Enter Organization ID")
    if org_id_input:
        try:
            org_id = int(org_id_input)
            matches = df[df['organization_id'] == org_id]['organization_name'].unique()
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

# Metric selection
selected_labels = st.multiselect(
    "Select metrics to visualize",
    ordered_labels,
    default=['Average Daily Inventory']
)

# Choose data variant
data_variant = st.selectbox(
    "Choose data version",
    ["Raw", "Zeros Replaced"]
)

# Smoothing method
smoothing_method = st.selectbox(
    "Choose smoothing method",
    ["None", "Exponential Moving Average", "Simple Moving Average"]
)

# Smoothing config
ema_span = sma_window = None
if smoothing_method == "Exponential Moving Average":
    ema_span = st.slider("Select EMA span (months)", min_value=2, max_value=12, value=3)
elif smoothing_method == "Simple Moving Average":
    sma_window = st.slider("Select SMA window (months)", min_value=2, max_value=12, value=3)

# Map labels to column names
selected_metrics = []
for label in selected_labels:
    base = label_to_metric[label]
    if data_variant == "Zeros Replaced":
        selected_metrics.append(f"{base}_zeros_replaced")
    else:
        selected_metrics.append(base)

# Plot button
if org_name and st.button("Show Plot"):
    plots = plot_organization_metrics_plotly(
        df,
        org_name,
        selected_metrics,
        data_variant,
        smoothing_method,
        ema_span,
        sma_window
    )
    for fig in plots:
        st.plotly_chart(fig, use_container_width=True)
