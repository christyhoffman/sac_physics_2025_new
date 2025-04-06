import streamlit as st
import pandas as pd
from matplotlib import pyplot as plt
import seaborn as sns

# --- PASSWORD PROTECTION ---
def check_password():
    def password_entered():
        # Compare entered password with secret
        if st.session_state["password"] == st.secrets["auth"]["password"]:
            st.session_state["auth_passed"] = True
        else:
            st.session_state["auth_passed"] = False

    # First-time password entry
    if "auth_passed" not in st.session_state:
        st.text_input("Enter password", type="password", on_change=password_entered, key="password")
        st.stop()

    # If password is incorrect
    elif not st.session_state["auth_passed"]:
        st.text_input("Enter password", type="password", on_change=password_entered, key="password")
        st.error("Incorrect password")
        st.stop()

check_password()

# --- LOAD DATA ---
@st.cache_data
def load_data():
	file_id = st.secrets["gdrive"]["file_id"]
	url = f"https://drive.google.com/file/d/{file_id}"
	df = pd.read_csv(url)
	return df

df = load_data()

# --- METRIC LABELS & ORDER ---
metric_label_map = {
    'CInventAvg': 'Average Daily Inventory',
    'DIntake': 'Daily Intake',
    'PAdopt': 'Percent Adopted',
    'PTransfer': 'Percent Transferred',
    'PNonlive': 'Percent Nonlive Outcomes',
    'LAggreg': 'Length of Stay',
    'SaveR': 'Save Rate'
}
label_to_metric = {v: k for k, v in metric_label_map.items()}

ordered_labels = [
    'Average Daily Inventory',
    'Daily Intake',
    'Percent Adopted',
    'Percent Transferred',
    'Percent Nonlive Outcomes',
    'Length of Stay',
    'Save Rate'
]

# --- PLOT FUNCTION ---
def plot_organization_metrics(df, org_name, metrics=['PAdopt'], title=None):
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
            continue
        fig, ax = plt.subplots(figsize=(12, 5))
        is_rate = metric not in count_metrics

        y_vals = org_data[metric] * 100 if is_rate and metric != 'LAggreg' else org_data[metric]

        display_name = metric_label_map.get(metric, metric)
        plot_title = title or f"{display_name} Over Time for {org_name}"

        # ✅ Set correct Y-axis label
        if metric == 'LAggreg':
            y_label = "Days"
        elif is_rate:
            y_label = "Percentage"
        else:
            y_label = "Count"

        ax.plot(org_data['yyyymmdd'], y_vals, marker='o', linewidth=2, color=sns.color_palette("Set2", 1)[0])
        ax.set_title(plot_title, fontsize=15, pad=15)
        ax.set_xlabel("Date", fontsize=12)
        ax.set_ylabel(y_label, fontsize=12)
        ax.set_ylim(bottom=0)

        if is_rate and metric != 'LAggreg':
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x:.2f}%'))

        ax.grid(True, linestyle='--', alpha=0.7)
        ax.tick_params(axis='x', rotation=45)
        ax.legend([display_name])
        plt.tight_layout()
        plots.append(fig)
    return plots

# --- USER INTERFACE ---
st.title("📊 Private Organization Metrics Dashboard")

# Input method
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
selected_metrics = [label_to_metric[label] for label in selected_labels]

# Plotting
if org_name and st.button("Show Plot"):
    plots = plot_organization_metrics(df, org_name, metrics=selected_metrics)
    for fig in plots:
        st.pyplot(fig)
