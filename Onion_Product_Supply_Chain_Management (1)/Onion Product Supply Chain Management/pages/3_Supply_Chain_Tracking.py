import streamlit as st

from agritrace.ui_helpers import get_service, refresh_data
from agritrace.security import ROLE_PERMISSIONS

st.title("🚚 Supply Chain Tracking")
service = get_service()
active_batches = [batch_id for batch_id, batch in service.batches.items() if batch["status"] == "ACTIVE"]

if not active_batches:
    st.info("Create an onion batch first in Batch Management.")
    st.stop()

batch_id = st.selectbox("Select active batch", sorted(active_batches))
batch = service.batches[batch_id]
st.write(f"**Current holder:** {batch['current_holder']}  |  **Current state:** {batch['current_state']}  |  **Quantity:** {batch['quantity_kg']:,.1f} kg")
actor_id = batch["current_holder"]
role = service.actors[actor_id]["role"]
events = sorted(ROLE_PERMISSIONS[role] - {"BATCH_CREATED", "BATCH_SPLIT", "BATCH_MERGED"})

with st.form("supply_event_form"):
    st.caption(f"The event will be signed by the current holder: {actor_id} ({role}).")
    event_type = st.selectbox("Supply-chain event", events)
    states = ["Andhra Pradesh", "Bihar", "Delhi", "Gujarat", "Karnataka", "Madhya Pradesh", "Maharashtra", "Rajasthan", "Uttar Pradesh"]
    to_state = st.selectbox("Destination / event state", states, index=states.index(batch["current_state"]) if batch["current_state"] in states else 0)
    recipient_options = [key for key in service.actors if key != actor_id]
    to_actor = ""
    if event_type == "OWNERSHIP_TRANSFER":
        to_actor = st.selectbox("Transfer batch to", recipient_options)
    note = st.text_input("Event notes", placeholder="Inspection passed, vehicle number, delivery note, etc.")
    submitted = st.form_submit_button("Record signed event", type="primary")
    if submitted:
        ok, message = service.add_event(
            actor_id=actor_id,
            batch_id=batch_id,
            event_type=event_type,
            to_state=to_state,
            to_actor=to_actor,
            details={"note": note} if note else {},
        )
        if ok:
            st.success(message)
            refresh_data()
            st.rerun()
        else:
            st.error(message)

st.subheader("Batch history")
history = service.get_batch_history(batch_id)
if history:
    st.dataframe(history, use_container_width=True, hide_index=True)
