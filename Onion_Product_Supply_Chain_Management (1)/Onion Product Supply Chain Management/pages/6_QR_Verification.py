import io
import json

import qrcode
import streamlit as st

from agritrace.ui_helpers import get_service

st.title("🔎 QR Batch Verification")
service = get_service()

if not service.batches:
    st.info("No batches are available. Create a batch first.")
    st.stop()

batch_id = st.selectbox("Select batch", sorted(service.batches))
qr_payload = json.dumps({"project": "Onion Product Supply Chain Management Across All States", "batch_id": batch_id})
qr_image = qrcode.make(qr_payload)
buffer = io.BytesIO()
qr_image.save(buffer, format="PNG")

left, right = st.columns([1, 2])
with left:
    st.image(buffer.getvalue(), caption=f"QR code for {batch_id}", width=220)
    st.download_button("Download QR code", buffer.getvalue(), f"{batch_id}.png", "image/png")
with right:
    st.code(qr_payload, language="json")
    ok, result = service.verify_batch(batch_id)
    if ok:
        st.success("Batch record found and blockchain integrity verified.")
        batch = result["batch"]
        st.metric("Quantity", f"{batch['quantity_kg']:,.1f} kg")
        st.write("Current holder:", batch["current_holder"])
        st.write("Current state:", batch["current_state"])
        st.write("Status:", batch["status"])
        st.write("Parent batches:", result["lineage"]["parents"] or "None")
        st.write("Child batches:", result["lineage"]["children"] or "None")
        st.subheader("Recorded journey")
        st.dataframe(result["history"], use_container_width=True, hide_index=True)
    else:
        st.error(result)

st.caption("The QR contains a batch identifier for lookup in this local prototype. It is not a public internet URL and does not physically authenticate the onion package.")
