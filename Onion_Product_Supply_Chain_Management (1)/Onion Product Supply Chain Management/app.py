import streamlit as st

from agritrace.ui_helpers import get_service, load_table
from config import DB_PATH, MARKET_FILE

st.set_page_config(
    page_title="Onion Product Supply Chain Management Across All States",
    page_icon="🌾",
    layout="wide",
)

service = get_service()
market_df = load_table("market_prices")
batches = load_table("batches")
blocks = load_table("blocks")
transactions = load_table("chain_transactions")
actors = load_table("actors")

st.title("🧅 Onion Product Supply Chain Management Across All States")
st.subheader("Blockchain-Based Onion Supply Chain Traceability and All-India Market Analytics")
st.caption("All-India onion market analytics | Multi-state onion batch traceability")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Onion market records", f"{len(market_df):,}")
col2.metric("States represented", int(market_df["state"].nunique()) if not market_df.empty else 0)
col3.metric("Blockchain blocks", len(blocks))
col4.metric("Tracked batches", len(batches))

st.divider()
left, right = st.columns([1.25, 1])
with left:
    st.subheader("Top states by market observations")
    if not market_df.empty:
        state_counts = market_df.groupby("state").size().sort_values(ascending=False).head(10)
        st.bar_chart(state_counts)
    else:
        st.info("Market data is not loaded. Check data/official/processed/all_india_onion_data.csv.")
with right:
    st.subheader("Blockchain health")
    if service.validate_chain():
        st.success("Blockchain integrity verified")
    else:
        st.error("Blockchain validation failed. Do not submit new transactions.")
    st.metric("Registered participants", len(actors))
    st.metric("Recorded transactions", len(transactions))

st.subheader("Recent blockchain activity")
if not transactions.empty:
    columns = [col for col in ["transaction_id", "batch_id", "event_type", "actor_id", "to_state", "quantity_kg", "timestamp", "record_origin"] if col in transactions.columns]
    st.dataframe(transactions[columns].tail(10), use_container_width=True, hide_index=True)
else:
    st.info("No supply-chain transactions have been recorded yet.")

st.caption(f"Database: {DB_PATH} | Processed market file: {MARKET_FILE}")
st.info("Use the pages in the left navigation to analyse market prices, register onion batches, record supply-chain events and verify the blockchain.")
