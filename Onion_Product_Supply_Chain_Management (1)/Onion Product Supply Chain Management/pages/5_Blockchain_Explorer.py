import json
import streamlit as st

from agritrace.ui_helpers import get_service, load_table

st.title("⛓️ Blockchain Explorer")
service = get_service()
blocks = load_table("blocks")
transactions = load_table("chain_transactions")

if service.validate_chain():
    st.success("The loaded blockchain passed integrity validation.")
else:
    st.error("Blockchain integrity validation failed.")

col1, col2 = st.columns(2)
col1.metric("Blocks", len(blocks))
col2.metric("Transactions", len(transactions))

if blocks.empty:
    st.info("No blocks are stored yet.")
else:
    for _, row in blocks.sort_values("block_index", ascending=False).iterrows():
        with st.expander(f"Block #{row['block_index']} | {row['current_hash'][:16]}..."):
            st.write("Timestamp:", row["timestamp"])
            st.write("Previous hash:", row["previous_hash"])
            st.write("Current hash:", row["current_hash"])
            st.json(json.loads(row["transactions_json"]))

st.subheader("Transaction ledger")
if not transactions.empty:
    st.dataframe(transactions.drop(columns=["transaction_json"], errors="ignore"), use_container_width=True, hide_index=True)
