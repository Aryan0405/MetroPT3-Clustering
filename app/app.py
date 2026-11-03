import json
import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
FULL_CSV = os.path.join(ROOT, "data", "processed", "metropt3_windows_with_clusters.csv")
DEMO_FILE = os.path.join(ROOT, "data", "processed", "metropt3_windows_demo.parquet")
METRICS_FILE = os.path.join(ROOT, "results", "metrics.json")
MAX_MB = 25

FAILURES = [
    ("2020-04-18 00:00", "2020-04-18 23:59", "Failure 1"),
    ("2020-05-29 23:30", "2020-05-30 06:00", "Failure 2"),
    ("2020-06-05 10:00", "2020-06-07 14:30", "Failure 3"),
    ("2020-07-15 14:30", "2020-07-15 19:00", "Failure 4"),
]

SENSORS = {
    "Motor_current_mean": "Motor current",
    "DV_pressure_mean": "DV pressure",
    "TP2_mean": "TP2",
    "TP3_mean": "TP3",
    "H1_mean": "H1",
    "Reservoirs_mean": "Reservoirs",
    "Oil_temperature_mean": "Oil temperature",
}


@st.cache_data
def load_metrics():
    with open(METRICS_FILE) as f:
        return json.load(f)


@st.cache_data
def load_windows():
    use_demo = (
        not os.path.exists(FULL_CSV)
        or os.path.getsize(FULL_CSV) / 1e6 > MAX_MB
    ) and os.path.exists(DEMO_FILE)
    if use_demo:
        df = pd.read_parquet(DEMO_FILE)
    else:
        df = pd.read_csv(FULL_CSV)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df, use_demo


def shade_failures(fig):
    for start, end, label in FAILURES:
        fig.add_vrect(
            x0=start, x1=end, fillcolor="red", opacity=0.12, line_width=0,
            layer="below", annotation_text=label, annotation_position="top left",
            annotation_font_size=10,
        )
    return fig


st.set_page_config(page_title="MetroPT-3 operating modes", layout="wide")
st.title("MetroPT-3 compressor operating modes")
st.caption("K-Means on 5-minute sensor windows, checked against four known air-leak failures.")

metrics = load_metrics()
windows, using_demo = load_windows()

st.header("Overview")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Windows", f"{metrics['n_windows']:,}")
c2.metric("Failure windows", f"{metrics['n_failures']:,}")
c3.metric("High-load share of windows", f"{metrics['high_load_share_percent']}%")
c4.metric("Failures within high load", f"{metrics['precision_high_load'] * 100:.1f}%")

shares = ", ".join(f"{k} {v}%" for k, v in metrics["mode_share_percent"].items())
st.write(f"Share of time in each mode: {shares}.")
st.write(
    f"{metrics['recall_high_load'] * 100:.1f}% of failure windows fall in the sustained high load "
    f"cluster, which covers {metrics['high_load_share_percent']}% of all windows "
    f"({metrics['lift_over_base']}x the overall failure rate)."
)

st.header("Sensor timeline")
sensor = st.selectbox("Sensor", list(SENSORS), format_func=SENSORS.get)

plot_df = windows.sort_values("timestamp")
if len(plot_df) > 4000:
    plot_df = plot_df.sample(n=4000, random_state=42).sort_values("timestamp")

fig = px.scatter(
    plot_df, x="timestamp", y=sensor, color="cluster_name", opacity=0.6,
    color_discrete_sequence=px.colors.qualitative.Set2,
    labels={sensor: SENSORS[sensor], "cluster_name": "Operating mode", "timestamp": "Time"},
)
shade_failures(fig)
fig.update_layout(height=450)
st.plotly_chart(fig, use_container_width=True)
st.caption("Red bands mark the four air-leak failure periods.")

st.header("Share of time vs share of failures")
high = metrics["high_load_share_percent"]
recall = round(metrics["recall_high_load"] * 100, 2)
share_df = pd.DataFrame({
    "Group": ["Sustained high load", "All other modes"],
    "Share of windows (%)": [high, round(100 - high, 2)],
    "Share of failure windows (%)": [recall, round(100 - recall, 2)],
})
fig2 = go.Figure()
fig2.add_bar(name="Share of windows", x=share_df["Group"], y=share_df["Share of windows (%)"])
fig2.add_bar(name="Share of failure windows", x=share_df["Group"], y=share_df["Share of failure windows (%)"])
fig2.update_layout(barmode="group", height=400, yaxis_title="Percent")
st.plotly_chart(fig2, use_container_width=True)

st.header("Sensor by operating mode")
fig3 = px.box(
    windows, x="cluster_name", y=sensor, color="cluster_name",
    color_discrete_sequence=px.colors.qualitative.Set2,
    labels={"cluster_name": "Operating mode", sensor: SENSORS[sensor]},
)
fig3.update_layout(showlegend=False, height=400)
st.plotly_chart(fig3, use_container_width=True)

st.header("Failure events")
st.dataframe(pd.DataFrame(metrics["failure_events"]), use_container_width=True, hide_index=True)

st.header("Limitations")
st.write("- Only four failures, all on one compressor.")
st.write("- A window counts as a failure if it overlaps any part of a failure period, so the labels cover the whole failure, not its start.")
st.write("- High load may be a symptom of the leak rather than a warning sign. This describes where failures happen; it does not predict them.")
st.write(
    f"- Only about {metrics['precision_high_load'] * 100:.0f}% of high-load windows are failure windows, "
    "so it would not work as an alarm."
)
st.write("- K-Means never saw the failure labels; they were compared with the clusters afterwards.")
if using_demo:
    st.write(
        f"- This live version uses a sample of {len(windows):,} windows. "
        f"The headline numbers come from all {metrics['n_windows']:,}."
    )