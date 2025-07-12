import streamlit as st
import pandas as pd
from matplotlib import pyplot as plt
import seaborn as sns
import urllib.error

# --- PASSWORD PROTECTION ---
def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets["auth"]["password"]:
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
    'CInventAvg': 'Average Daily Inventory',
    'DIntake': 'Daily Intake',
    'PAdopt_monthly': 'Animal's Probability of Adoption During Month',
    'PTransfer_monthly': 'Animal's Probability of Transfer During Month',
    'PNonlive_monthly': 'Animal's Probability of a Nonlive Outcome During Month',
    'LAggreg': 'Length of Stay',
    'SaveR': 'Save Rate'
}
label_to_metric = {v: k for k, v in metric_label_map.items()}

ordered_labels = [
    'Average Daily Inventory',
    'Daily Intake',
    'Monthly Probability of Adoption',
    'Monthly Probability of Transfer',
    'Monthly Probability of Nonlive Outcome',
    'Length of Stay',
    'Save Rate'
]

# --- PLOT FUNCTION ---
def plot_organization_metrics(df, org_name, metrics=['PAdopt_monthly'], title=None, data_variant="Raw"):
    sns.set(style='whitegrid')
    org_data = df[df['organization_name'] == org_name].copy()

    if org_data.empty:
        st.warning(f"No data found for organization: {org_name}")
        return []

    if not pd.api.types.is_datetime64_any_dtype(org_data['yyyymmdd']):
        org_data['yyyymmdd'] = pd.to_datetime(org_data['yyyymmdd'])

    count_metrics = {'DIntake', 'CInventAvg', 'LAggreg'}
    plots = []

    for metric in metrics:
        if metric not in org_data.columns:
            st.warning(f"Metric {metric} not found in data.")
            continue

        fig, ax = plt.subplots(figsize=(12, 5))

        # Determine if this is a rate metric
        is_rate = not any(metric.startswith(m) for m in count_metrics)

        # Cap percentage values at 100
        if is_rate and not metric.startswith('LAggreg'):
            y_vals = org_data[metric] * 100
            y_vals = y_vals.clip(upper=100)
        else:
            y_vals = org_data[metric]

        base_metric = metric.replace('_interpolated', '').replace('_zeros_replaced', '')
        display_name = metric_label_map.get(base_metric, metric)

        variant_suffix = {
            "Interpolated": " (Interpolated)",
            "Zeros Replaced": " (Zeros Replaced)",
            "Raw": ""
        }
        plot_title = title or f"{display_name}{variant_suffix[data_variant]} Over Time for {org_name}"

        y_label = "Days" if base_metric == 'LAggreg' else "Percentage" if is_rate else "Count"

        ax.plot(org_data['yyyymmdd'], y_vals, marker='o', linewidth=2, color=sns.color_palette("Set2", 1)[0])
        ax.set_title(plot_title, fontsize=15, pad=15)
        ax.set_xlabel("Date", fontsize=12)
        ax.set_ylabel(y_label, fontsize=12)

        if is_rate and base_metric != 'LAggreg':
            ax.set_ylim(0, 100)
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x:.2f}%'))
        else:
            ax.set_ylim(bottom=0)

        ax.grid(True, linestyle='--', alpha=0.7)
        ax.tick_params(axis='x', rotation=45)
        ax.legend([display_name])
        plt.tight_layout()
        plots.append(fig)

    return plots

# --- USER INTERFACE ---
st.title("📊 Shelter Metrics Dashboard")

# Organization selection
selection_mode = st.radio("Choose organization selection method:", ["By Name", "By ID"])
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
data_variant = st.selectbox("Choose data version", ["Raw", "Interpolated", "Zeros Replaced"])

# Map labels to the correct column names based on the variant
selected_metrics = []
for label in selected_labels:
    metric_base = label_to_metric[label]
    if data_variant == "Interpolated":
        metric_name = f"{metric_base}_interpolated"
    elif data_variant == "Zeros Replaced":
        metric_name = f"{metric_base}_zeros_replaced"
    else:
        metric_name = metric_base
    selected_metrics.append(metric_name)

# Plot button
if org_name and st.button("Show Plot"):
    plots = plot_organization_metrics(df, org_name, metrics=selected_metrics, data_variant=data_variant)
    for fig in plots:
        st.pyplot(fig)
