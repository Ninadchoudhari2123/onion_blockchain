import base64
import copy

import pandas as pd
import streamlit as st

from agritrace.ui_helpers import get_service

st.title("🛡️ Blockchain Tampering Detection")
st.caption(
    "Multi-layer verification of block hashes, transaction signatures, participant permissions "
    "and the SQLite transaction index."
)
service = get_service()
report = service.audit_chain()

hash_ok = report["blockchain"]["valid"]
signatures_ok = report["signatures"]["valid"]
permissions_ok = report["permissions"]["valid"]
database_ok = report["database"]["valid"] if report["database"]["checked"] else None
actors_ok = report["actor_registry"]["valid"] if report["actor_registry"]["checked"] else None

if report["overall_valid"]:
    st.success("Full integrity audit passed. No mismatch was found in the stored records.")
else:
    st.error("Integrity audit found one or more problems. Review the findings below before recording new events.")

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Block hash chain", "PASS" if hash_ok else "ISSUES")
col2.metric("Digital signatures", "PASS" if signatures_ok else "ISSUES")
col3.metric("Role permissions", "PASS" if permissions_ok else "ISSUES")
col4.metric("SQL ledger sync", "PASS" if database_ok else ("ISSUES" if database_ok is False else "N/A"))
col5.metric("Participant keys", "PASS" if actors_ok else ("ISSUES" if actors_ok is False else "N/A"))

st.caption(
    f"Blocks checked: {report['blocks_checked']} | "
    f"Signed transactions checked: {report['signatures']['checked']} | "
    f"SQL transactions: {report['database']['records_checked']} | "
    f"Batch snapshots: {report['database']['batches_checked']} | "
    f"Lineage links: {report['database']['lineage_links_checked']}"
)

st.subheader("What each verification layer checks")
with st.expander("1. Block hash and chain-link verification", expanded=True):
    st.write(
        "Recalculates each block's SHA-256 hash, checks its block number, confirms the genesis "
        "block starts with previous hash 0, and verifies that every later block points to the "
        "hash of the block before it."
    )
with st.expander("2. Ed25519 signature and role verification"):
    st.write(
        "Verifies each transaction signature using the registered participant's public key. "
        "It also checks whether the participant's role is allowed to record that event type. "
        "Changing a signed transaction and rebuilding its hashes does not create a valid signature."
    )
with st.expander("3. SQLite ledger and participant registry comparison"):
    st.write(
        "Compares each transaction in the blockchain with its corresponding SQL ledger row, "
        "including the transaction JSON, block number and displayed fields. It replays batch "
        "creation, transfers, delivery, splitting and merging to compare the saved batch snapshots "
        "and parent-child lineage. It also checks participant roles and public keys."
    )

st.subheader("Audit findings")
if report["issues"]:
    finding_rows = [
        {
            "Category": item.get("category", "GENERAL"),
            "Code": item.get("code", "CHECK_FAILED"),
            "Block": item.get("block_index", "—"),
            "Transaction": item.get("transaction_id", "—"),
            "Finding": item.get("message", "Integrity check failed."),
        }
        for item in report["issues"]
    ]
    st.dataframe(pd.DataFrame(finding_rows), use_container_width=True, hide_index=True)
else:
    st.info("No audit findings. All available checks passed.")

st.divider()
st.subheader("Safe attack simulation")
st.write(
    "Choose an example attack and run it against a temporary copy of the stored chain. "
    "The simulation does not update the live blockchain or SQLite database."
)

attack_options = {
    "Edit transaction data without updating its hash": "payload_without_rehash",
    "Edit transaction data and rebuild the hash chain": "payload_with_rehash",
    "Change a previous-block link and rebuild hashes": "previous_link", 
    "Forge a transaction signature and rebuild hashes": "signature",
}

stored_chain = service.get_persisted_chain()
target_choices = {}
for block in stored_chain.chain:
    if block.index == 0 or not isinstance(block.transactions, list):
        continue
    for tx_position, tx in enumerate(block.transactions):
        if isinstance(tx, dict) and tx.get("transaction_id"):
            label = (
                f"Block {block.index} | {tx.get('batch_id', 'Unknown batch')} | "
                f"{tx.get('event_type', 'Unknown event')} | {tx['transaction_id'][:18]}"
            )
            target_choices[label] = (block.index, tx_position)

if not target_choices:
    st.info("Create at least one onion batch or supply-chain event to run the simulation.")
else:
    attack_label = st.selectbox("Select attack scenario", list(attack_options.keys()))
    transaction_label = st.selectbox("Select transaction to test", list(target_choices.keys()))

    def recalculate_forward(test_chain, start_index):
        """Rebuild hashes from a changed block onward, like an attacker might try."""
        for position in range(start_index, len(test_chain.chain)):
            block = test_chain.chain[position]
            if position > start_index:
                block.previous_hash = test_chain.chain[position - 1].hash
            block.hash = block.calculate_hash()

    if st.button("Run safe tampering simulation", type="primary"):
        test_chain = copy.deepcopy(stored_chain)
        block_index, tx_position = target_choices[transaction_label]
        target_block = test_chain.chain[block_index]
        target_tx = target_block.transactions[tx_position]
        scenario = attack_options[attack_label]

        if scenario in {"payload_without_rehash", "payload_with_rehash"}:
            old_quantity = target_tx.get("quantity_kg")
            if isinstance(old_quantity, (int, float)) and not isinstance(old_quantity, bool):
                target_tx["quantity_kg"] = float(old_quantity) + 1.0
                change_text = f"quantity_kg changed from {old_quantity} to {target_tx['quantity_kg']}"
            else:
                target_tx["tamper_demo_field"] = "UNAUTHORIZED CHANGE"
                change_text = "an unauthorized field was added to the transaction"
            if scenario == "payload_with_rehash":
                recalculate_forward(test_chain, block_index)
        elif scenario == "previous_link":
            target_block.previous_hash = "f" * 64
            recalculate_forward(test_chain, block_index)
            change_text = f"Block {block_index} previous_hash was replaced with a fake hash"
        else:
            target_tx["signature"] = base64.b64encode(b"\x00" * 64).decode("ascii")
            recalculate_forward(test_chain, block_index)
            change_text = "the transaction signature was replaced with a forged value"

        simulated_report = service.audit_chain(chain_override=test_chain)
        st.write("**Simulated change:**", change_text)

        sim_col1, sim_col2 = st.columns(2)
        sim_col1.metric(
            "Hash-chain verification",
            "PASS" if simulated_report["blockchain"]["valid"] else "DETECTED",
        )
        sim_col2.metric(
            "Signature verification",
            "PASS" if simulated_report["signatures"]["valid"] else "DETECTED",
        )

        if simulated_report["overall_valid"]:
            st.error("The simulated change was not detected. Review the audit implementation.")
        else:
            st.success("Tampering detected by the verification checks.")
            for item in simulated_report["issues"]:
                st.write(f"**{item.get('code', 'ISSUE')}** — {item.get('message', '')}")
        st.caption(
            "Only the temporary in-memory copy was changed. The original chain and saved database were not modified."
        )

st.warning(
    "Prototype limitation: this is a local, single-node blockchain. These checks detect changed "
    "stored records, broken links, invalid signatures and SQL ledger mismatches. Without an "
    "independent external checkpoint or distributed network, a complete deletion of the newest "
    "blocks or replacement of the entire local database cannot be conclusively detected."
)
