import streamlit as st
import pandas as pd

from agritrace.ui_helpers import get_service, load_table, refresh_data

st.title("📦 Onion Batch Management")
service = get_service()
batches_df = load_table("batches")

with st.expander("Register a new onion batch", expanded=batches_df.empty):
    with st.form("create_batch_form"):
        actor_id = st.selectbox("Farmer", [actor_id for actor_id, actor in service.actors.items() if actor["role"] == "FARMER"])
        batch_id = st.text_input("Batch ID", placeholder="ON-IND-1001")
        quantity = st.number_input("Quantity (kg)", min_value=1.0, value=1000.0, step=50.0)
        state = st.selectbox("Farm state", ["Andhra Pradesh", "Bihar", "Gujarat", "Karnataka", "Madhya Pradesh", "Maharashtra", "Rajasthan", "Uttar Pradesh", "Delhi"])
        district = st.text_input("District", value="Nashik")
        harvest_date = st.date_input("Harvest date")
        variety = st.text_input("Onion variety", value="Local")
        submitted = st.form_submit_button("Create and record batch", type="primary")
        if submitted:
            ok, message = service.create_batch(actor_id, batch_id.strip(), quantity, state, district, str(harvest_date), variety)
            if ok:
                st.success(message)
                refresh_data()
                st.rerun()
            else:
                st.error(message)

st.subheader("Registered batches")
batches_df = load_table("batches")
if batches_df.empty:
    st.info("No batches registered yet.")
else:
    st.dataframe(batches_df, use_container_width=True, hide_index=True)
    selected_id = st.selectbox("View batch details", batches_df["batch_id"].tolist())
    ok, result = service.verify_batch(selected_id)
    if ok:
        batch = result["batch"]
        col1, col2, col3 = st.columns(3)
        col1.metric("Quantity", f"{batch['quantity_kg']:,.1f} kg")
        col2.metric("Current holder", batch["current_holder"])
        col3.metric("Current state", batch["current_state"])
        st.write("Status:", batch["status"])
        st.write("Parent batches:", ", ".join(result["lineage"]["parents"]) or "None")
        st.write("Child batches:", ", ".join(result["lineage"]["children"]) or "None")
