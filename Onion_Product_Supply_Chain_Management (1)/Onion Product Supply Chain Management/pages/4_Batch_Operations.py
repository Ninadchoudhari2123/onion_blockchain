import streamlit as st

from agritrace.ui_helpers import get_service, refresh_data

st.title("🔀 Batch Splitting and Merging")
service = get_service()

split_tab, merge_tab = st.tabs(["Split a batch", "Merge batches"])

with split_tab:
    st.write("Split an active batch into child batches. The current holder must be a farmer, collection centre or wholesaler. Child quantities must add up to the parent quantity.")
    active_batches = [key for key, value in service.batches.items() if value["status"] == "ACTIVE"]
    if active_batches:
        with st.form("split_form"):
            parent_id = st.selectbox("Parent batch", sorted(active_batches))
            parent = service.batches[parent_id]
            st.caption(f"Current holder: {parent['current_holder']} | Quantity: {parent['quantity_kg']} kg")
            child_a = st.text_input("Child batch A ID", value=f"{parent_id}-A")
            qty_a = st.number_input("Child A quantity (kg)", min_value=0.0, value=parent["quantity_kg"] * 0.6)
            child_b = st.text_input("Child batch B ID", value=f"{parent_id}-B")
            qty_b = st.number_input("Child B quantity (kg)", min_value=0.0, value=parent["quantity_kg"] * 0.4)
            submitted = st.form_submit_button("Split batch", type="primary")
            if submitted:
                ok, message = service.split_batch(
                    parent["current_holder"], parent_id,
                    [{"batch_id": child_a.strip(), "quantity_kg": qty_a},
                     {"batch_id": child_b.strip(), "quantity_kg": qty_b}],
                )
                if ok:
                    st.success(message)
                    refresh_data()
                    st.rerun()
                else:
                    st.error(message)
    else:
        st.info("No active batches available.")

with merge_tab:
    st.write("Merge two or more active batches held by the same farmer, collection centre or wholesaler at the same state/location.")
    active_batches = [key for key, value in service.batches.items() if value["status"] == "ACTIVE"]
    if len(active_batches) >= 2:
        with st.form("merge_form"):
            parent_ids = st.multiselect("Select parent batches", sorted(active_batches), max_selections=5)
            new_batch_id = st.text_input("New merged batch ID", placeholder="ON-IND-MERGED-001")
            submitted = st.form_submit_button("Merge batches", type="primary")
            if submitted:
                if not parent_ids:
                    st.error("Select at least two parent batches.")
                else:
                    holders = {service.batches[key]["current_holder"] for key in parent_ids}
                    if len(holders) != 1:
                        st.error("All selected batches must have the same current holder.")
                    else:
                        actor_id = next(iter(holders))
                        ok, message = service.merge_batches(actor_id, parent_ids, new_batch_id.strip())
                        if ok:
                            st.success(message)
                            refresh_data()
                            st.rerun()
                        else:
                            st.error(message)
    else:
        st.info("At least two active batches are required for merging.")
