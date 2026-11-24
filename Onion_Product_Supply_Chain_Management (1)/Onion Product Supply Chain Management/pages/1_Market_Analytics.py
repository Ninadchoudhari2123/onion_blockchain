import streamlit as st
import pandas as pd
import plotly.express as px

from agritrace.ui_helpers import load_table

st.title("📊 All-India Onion Market Analytics")
market_df = load_table("market_prices")

if market_df.empty:
    st.warning("No market observations found. Check the official CSV in data/official/raw/.")
    st.stop()

for col in ["min_price", "max_price", "modal_price"]:
    market_df[col] = pd.to_numeric(market_df[col], errors="coerce")

market_df["arrival_date"] = pd.to_datetime(market_df["arrival_date"], errors="coerce")
st.caption("Source: AGMARKNET / data.gov.in. Price observations are real source records; they are not batch-tracking events.")

states = sorted(market_df["state"].dropna().unique().tolist())
selected_states = st.multiselect("Filter by state", states, default=states)
filtered_df = market_df[market_df["state"].isin(selected_states)].copy()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Observations", f"{len(filtered_df):,}")
col2.metric("States", filtered_df["state"].nunique())
col3.metric("Districts", filtered_df["district"].nunique())
col4.metric("Markets", filtered_df["market"].nunique())

if not filtered_df.empty:
    state_summary = (
        filtered_df.groupby("state", as_index=False)
        .agg(avg_modal_price=("modal_price", "mean"), records=("modal_price", "size"))
        .sort_values("avg_modal_price", ascending=False)
    )
    left, right = st.columns(2)
    with left:
        st.subheader("Average modal price by state")
        chart_df = state_summary.sort_values("avg_modal_price", ascending=True)
        fig = px.bar(chart_df, x="avg_modal_price", y="state", orientation="h", labels={"avg_modal_price": "₹ per quintal", "state": "State"})
        st.plotly_chart(fig, use_container_width=True)
    with right:
        st.subheader("Market observations by state")
        count_df = filtered_df.groupby("state", as_index=False).size().sort_values("size", ascending=False)
        fig = px.bar(count_df, x="state", y="size", labels={"size": "Records", "state": "State"})
        fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Market-level prices")
    market_summary = (
        filtered_df.groupby(["state", "district", "market"], as_index=False)
        .agg(min_price=("min_price", "mean"), max_price=("max_price", "mean"), modal_price=("modal_price", "mean"), records=("modal_price", "size"))
        .sort_values("modal_price", ascending=False)
    )
    st.dataframe(market_summary, use_container_width=True, hide_index=True)
    st.download_button("Download filtered market data", filtered_df.to_csv(index=False).encode("utf-8"), "filtered_onion_market_data.csv", "text/csv")

    dates = filtered_df["arrival_date"].dropna()
    if not dates.empty:
        st.caption(f"Arrival-date coverage in this downloaded file: {dates.min().date()} to {dates.max().date()} ({dates.nunique()} distinct date(s)).")
