# Tampering Detection Enhancement

## What changed

The Tampering Detection page now performs a multi-layer audit:

1. **Block integrity:** recalculates every SHA-256 block hash, checks block order, validates the genesis block and confirms each block references the previous block's stored hash.
2. **Transaction authenticity:** verifies Ed25519 signatures using the registered participant's public key.
3. **Role permissions:** checks that the participant's role is allowed to record the transaction event type.
4. **SQL ledger consistency:** compares each transaction in the blockchain with its corresponding `chain_transactions` row, including the JSON payload, block index and indexed fields. It also detects missing and extra ledger rows.
5. **Batch and lineage consistency:** replays batch creation, transfers, delivery, splitting and merging from the blockchain, then compares the reconstructed batch snapshots and parent-child links with the saved SQLite tables.
6. **Participant registry:** checks stored public keys and roles against the local key registry and the project's default demo role policy.

New blockchain operations are blocked when the persisted audit fails.

## How to demonstrate it

1. Start the app with `streamlit run app.py`.
2. Open **Tampering Detection** in the sidebar.
3. Review the five audit indicators at the top of the page.
4. Choose a transaction and an attack scenario.
5. Click **Run safe tampering simulation**.
6. Read the findings shown below the simulation.

The simulation works on a deep copy of the stored chain. It does not change the live chain or SQLite database.

### Demonstration scenarios

- **Edit transaction without updating its hash:** the recalculated block hash no longer matches the stored hash.
- **Edit transaction and rebuild the hash chain:** the chain links can be rebuilt, but the original Ed25519 signature no longer matches the changed transaction.
- **Change a previous-block link:** the affected block no longer points to the actual previous block hash.
- **Forge a transaction signature:** the signature verification fails even when the block hashes are rebuilt.

## Important limitation

This remains a local, single-node educational prototype. A hash chain and digital signatures can detect many changes to stored data, but they are not an external source of truth. Without an independently protected checkpoint, distributed validators or trusted backups, a complete deletion of the newest blocks or replacement of the entire local database and key material cannot be conclusively detected. The audit also reconstructs the saved batch snapshots and lineage from blockchain events. It does not prove that a physical onion shipment or manually entered event is true.

## Validation performed

The included automated test suite passed **17 tests** after these changes (`pytest -q`). The Streamlit interface source was syntax-compiled; Streamlit itself was not installed in the editing environment, so a browser-based UI launch was not performed here.
