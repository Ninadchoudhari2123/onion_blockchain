from datetime import datetime, timezone
import json
import math

from .blockchain import Blockchain, canonical_json
from .database import get_connection, init_db, load_blocks, load_batches, load_lineage, save_service_state
from .security import ROLE_PERMISSIONS, create_transaction, load_or_create_actor, verify_transaction_signature

DEFAULT_ACTORS = {
    "farmer_001": "FARMER",
    "center_001": "COLLECTION_CENTER",
    "transporter_001": "TRANSPORTER",
    "wholesaler_001": "WHOLESALER",
    "retailer_001": "RETAILER",
}


class AgriTraceService:
    def __init__(self, db_path, key_dir):
        self.db_path = db_path
        self.key_dir = key_dir
        init_db(db_path)
        with get_connection(db_path) as conn:
            self.chain = Blockchain(load_blocks(conn))
            self.batches = load_batches(conn)
            self.lineage = load_lineage(conn, self.batches)
            actor_rows = conn.execute("SELECT actor_id, role FROM actors").fetchall()
            saved_roles = {row["actor_id"]: row["role"] for row in actor_rows}

        self.actors = {}
        for actor_id, role in DEFAULT_ACTORS.items():
            actor = load_or_create_actor(actor_id, saved_roles.get(actor_id, role), key_dir)
            self.actors[actor_id] = actor
        self.batch_history = self._build_history()
        self._save()

    def _build_history(self):
        history = {}
        for block in self.chain.chain:
            for tx in block.transactions:
                batch_id = tx.get("batch_id")
                if batch_id:
                    history.setdefault(batch_id, []).append(tx)
        return history

    def _save(self):
        save_service_state(
            self.db_path,
            self.chain,
            self.actors,
            self.batches,
            self.lineage,
        )

    def validate_chain(self):
        return self.chain.validate_chain()

    def get_persisted_chain(self):
        """Reload the stored blocks so audits do not rely only on cached memory."""
        with get_connection(self.db_path) as conn:
            blocks = load_blocks(conn)
        return Blockchain(blocks, create_genesis=False)

    def _replay_traceability_state(self, chain):
        """Reconstruct batch snapshots and lineage solely from signed chain events."""
        batches = {}
        lineage = {}
        issues = []

        def ensure_lineage(batch_id):
            lineage.setdefault(batch_id, {"parents": set(), "children": set()})

        def safe_quantity(value, block_index, batch_id):
            try:
                quantity = float(value)
            except (TypeError, ValueError):
                quantity = 0.0
            if not math.isfinite(quantity) or quantity <= 0:
                issues.append({
                    "code": "BATCH_REPLAY_QUANTITY_INVALID",
                    "category": "TRANSACTION",
                    "severity": "ERROR",
                    "block_index": block_index,
                    "message": f"Transaction for batch '{batch_id}' contains an invalid quantity.",
                })
                return 0.0
            return quantity

        for block in chain.chain:
            block_transactions = block.transactions if isinstance(block.transactions, list) else []
            for tx in block_transactions:
                if not isinstance(tx, dict) or (
                    block.index == 0 and tx.get("event") == "Genesis Block"
                ):
                    continue

                event_type = tx.get("event_type")
                batch_id = tx.get("batch_id")
                actor_id = tx.get("actor_id")
                details = tx.get("details") or {}

                if not isinstance(batch_id, str) or not batch_id:
                    issues.append({
                        "code": "BATCH_REPLAY_BATCH_ID_INVALID",
                        "category": "TRANSACTION",
                        "severity": "ERROR",
                        "block_index": block.index,
                        "message": "A supply-chain transaction contains an empty or invalid batch ID.",
                    })
                    continue

                if event_type == "BATCH_CREATED":
                    if batch_id in batches:
                        issues.append({
                            "code": "BATCH_REPLAY_CREATE_CONFLICT",
                            "category": "TRANSACTION",
                            "severity": "ERROR",
                            "block_index": block.index,
                            "message": f"Batch creation for '{batch_id}' is missing an ID or duplicates an existing batch.",
                        })
                        continue
                    batches[batch_id] = {
                        "quantity_kg": safe_quantity(tx.get("quantity_kg"), block.index, batch_id),
                        "current_holder": actor_id,
                        "current_state": tx.get("to_state", ""),
                        "status": "ACTIVE",
                        "record_origin": tx.get("record_origin", "DEMO"),
                    }
                    ensure_lineage(batch_id)

                elif event_type == "BATCH_SPLIT":
                    parent = batches.get(batch_id)
                    children = details.get("child_batches", []) if isinstance(details, dict) else []
                    if parent is None or not isinstance(children, list) or not isinstance(details, dict):
                        issues.append({
                            "code": "BATCH_REPLAY_SPLIT_INVALID",
                            "category": "TRANSACTION",
                            "severity": "ERROR",
                            "block_index": block.index,
                            "message": f"Split transaction for batch '{batch_id}' cannot be reconstructed.",
                        })
                        continue
                    parent["status"] = "SPLIT"
                    ensure_lineage(batch_id)
                    for child in children:
                        child_id = child.get("batch_id") if isinstance(child, dict) else None
                        child_quantity = child.get("quantity_kg") if isinstance(child, dict) else None
                        if not isinstance(child_id, str) or not child_id or child_id in batches:
                            issues.append({
                                "code": "BATCH_REPLAY_CHILD_CONFLICT",
                                "category": "TRANSACTION",
                                "severity": "ERROR",
                                "block_index": block.index,
                                "message": f"Split transaction contains an empty or duplicate child ID for parent '{batch_id}'.",
                            })
                            continue
                        batches[child_id] = {
                            "quantity_kg": safe_quantity(child_quantity, block.index, child_id),
                            "current_holder": actor_id,
                            "current_state": parent["current_state"],
                            "status": "ACTIVE",
                            "record_origin": tx.get("record_origin", "DEMO"),
                        }
                        ensure_lineage(child_id)
                        lineage[batch_id]["children"].add(child_id)
                        lineage[child_id]["parents"].add(batch_id)

                elif event_type == "BATCH_MERGED":
                    parent_ids = details.get("parent_batches", []) if isinstance(details, dict) else []
                    if (
                        not isinstance(parent_ids, list)
                        or not parent_ids
                        or any(not isinstance(parent_id, str) or not parent_id for parent_id in parent_ids)
                    ):
                        issues.append({
                            "code": "BATCH_REPLAY_MERGE_INVALID",
                            "category": "TRANSACTION",
                            "severity": "ERROR",
                            "block_index": block.index,
                            "message": f"Merge transaction for batch '{batch_id}' has no valid parent list.",
                        })
                        continue
                    valid_parents = True
                    for parent_id in parent_ids:
                        parent = batches.get(parent_id)
                        if parent is None:
                            valid_parents = False
                            issues.append({
                                "code": "BATCH_REPLAY_PARENT_MISSING",
                                "category": "TRANSACTION",
                                "severity": "ERROR",
                                "block_index": block.index,
                                "message": f"Merge transaction references missing parent batch '{parent_id}'.",
                            })
                            continue
                        parent["status"] = "MERGED"
                        ensure_lineage(parent_id)
                    if not batch_id or batch_id in batches:
                        valid_parents = False
                        issues.append({
                            "code": "BATCH_REPLAY_MERGED_ID_CONFLICT",
                            "category": "TRANSACTION",
                            "severity": "ERROR",
                            "block_index": block.index,
                            "message": f"Merged batch ID '{batch_id}' is empty or already exists.",
                        })
                    if valid_parents:
                        for parent_id in parent_ids:
                            lineage[parent_id]["children"].add(batch_id)
                        batches[batch_id] = {
                            "quantity_kg": safe_quantity(tx.get("quantity_kg"), block.index, batch_id),
                            "current_holder": actor_id,
                            "current_state": tx.get("to_state", tx.get("from_state", "")),
                            "status": "ACTIVE",
                            "record_origin": tx.get("record_origin", "DEMO"),
                        }
                        ensure_lineage(batch_id)
                        lineage[batch_id]["parents"].update(parent_ids)

                elif batch_id in batches:
                    batch = batches[batch_id]
                    if event_type == "OWNERSHIP_TRANSFER":
                        batch["current_holder"] = tx.get("to_actor")
                        batch["current_state"] = tx.get("to_state", batch["current_state"])
                    elif event_type == "DELIVERED":
                        batch["current_state"] = tx.get("to_state", batch["current_state"])
                else:
                    issues.append({
                        "code": "BATCH_REPLAY_REFERENCE_MISSING",
                        "category": "TRANSACTION",
                        "severity": "ERROR",
                        "block_index": block.index,
                        "message": f"Transaction references batch '{batch_id}' before it can be reconstructed.",
                    })

        return batches, lineage, issues

    def audit_chain(self, chain_override=None):
        """Audit block links, Ed25519 signatures and persisted transaction indexes.

        Passing chain_override audits an isolated in-memory test copy and deliberately
        skips database comparisons, so attack demonstrations never write to SQLite.
        """
        database_rows = []
        batch_rows = []
        lineage_rows = []
        actor_rows = []
        if chain_override is None:
            with get_connection(self.db_path) as conn:
                stored_blocks = load_blocks(conn)
                database_rows = conn.execute(
                    "SELECT * FROM chain_transactions ORDER BY transaction_id"
                ).fetchall()
                batch_rows = conn.execute(
                    "SELECT * FROM batches ORDER BY batch_id"
                ).fetchall()
                lineage_rows = conn.execute(
                    "SELECT * FROM batch_lineage ORDER BY parent_batch_id, child_batch_id"
                ).fetchall()
                actor_rows = conn.execute(
                    "SELECT actor_id, role, public_key FROM actors ORDER BY actor_id"
                ).fetchall()
            chain = Blockchain(stored_blocks, create_genesis=False)
            check_database = True
        else:
            chain = chain_override
            check_database = False

        chain_result = chain.validate_chain_detailed()
        issues = [
            {**item, "category": "BLOCKCHAIN", "severity": "ERROR"}
            for item in chain_result["issues"]
        ]

        signatures_checked = 0
        signatures_valid = 0
        seen_transaction_ids = set()
        expected_transactions = {}

        for block in chain.chain:
            block_transactions = block.transactions if isinstance(block.transactions, list) else []
            for tx in block_transactions:
                if not isinstance(tx, dict):
                    issues.append({
                        "code": "INVALID_TRANSACTION_FORMAT",
                        "category": "TRANSACTION",
                        "severity": "ERROR",
                        "block_index": block.index,
                        "message": "A block contains a transaction that is not a JSON object.",
                    })
                    continue
                if block.index == 0 and tx.get("event") == "Genesis Block":
                    continue

                transaction_id = tx.get("transaction_id")
                actor_id = tx.get("actor_id")
                if isinstance(transaction_id, str) and transaction_id:
                    if transaction_id in seen_transaction_ids:
                        issues.append({
                            "code": "DUPLICATE_TRANSACTION_ID",
                            "category": "TRANSACTION",
                            "severity": "ERROR",
                            "block_index": block.index,
                            "transaction_id": transaction_id,
                            "message": f"Transaction ID {transaction_id} appears more than once.",
                        })
                    seen_transaction_ids.add(transaction_id)
                    expected_transactions[transaction_id] = (block.index, tx)
                else:
                    issues.append({
                        "code": "MISSING_TRANSACTION_ID",
                        "category": "TRANSACTION",
                        "severity": "ERROR",
                        "block_index": block.index,
                        "message": "A non-genesis transaction has no transaction ID.",
                    })

                signatures_checked += 1
                actor = self.actors.get(actor_id) if isinstance(actor_id, str) else None
                if actor is None:
                    issues.append({
                        "code": "UNKNOWN_TRANSACTION_ACTOR",
                        "category": "SIGNATURE",
                        "severity": "ERROR",
                        "block_index": block.index,
                        "transaction_id": transaction_id,
                        "message": f"No registered public key is available for actor '{actor_id}'.",
                    })
                    continue

                if verify_transaction_signature(tx, actor["public_key"]):
                    signatures_valid += 1
                else:
                    issues.append({
                        "code": "INVALID_TRANSACTION_SIGNATURE",
                        "category": "SIGNATURE",
                        "severity": "ERROR",
                        "block_index": block.index,
                        "transaction_id": transaction_id,
                        "message": (
                            f"The Ed25519 signature for transaction {transaction_id or '(missing ID)'} "
                            "does not match its contents and registered actor key."
                        ),
                    })

                role = actor["role"]
                event_type = tx.get("event_type")
                allowed_events = ROLE_PERMISSIONS.get(role, set()) if isinstance(role, str) else set()
                if not isinstance(event_type, str) or event_type not in allowed_events:
                    issues.append({
                        "code": "ROLE_PERMISSION_VIOLATION",
                        "category": "PERMISSIONS",
                        "severity": "ERROR",
                        "block_index": block.index,
                        "transaction_id": transaction_id,
                        "message": f"Actor '{actor_id}' with role '{role}' is not permitted to record '{tx.get('event_type')}'.",
                    })

        replayed_batches, replayed_lineage, replay_issues = self._replay_traceability_state(chain)
        issues.extend(replay_issues)

        database_result = {
            "checked": False, "valid": None, "records_checked": 0,
            "batches_checked": 0, "lineage_links_checked": 0, "issues": [],
        }
        actor_registry_result = {"checked": False, "valid": None, "actors_checked": 0, "issues": []}

        if check_database:
            database_issues = []
            actual_by_id = {row["transaction_id"]: row for row in database_rows}
            expected_ids = set(expected_transactions)
            actual_ids = set(actual_by_id)

            for missing_id in sorted(expected_ids - actual_ids, key=str):
                database_issues.append({
                    "code": "LEDGER_ROW_MISSING",
                    "category": "DATABASE",
                    "severity": "ERROR",
                    "transaction_id": missing_id,
                    "message": f"Transaction {missing_id} exists in a block but is missing from the SQL transaction ledger.",
                })
            for extra_id in sorted(actual_ids - expected_ids, key=str):
                database_issues.append({
                    "code": "LEDGER_ROW_EXTRA",
                    "category": "DATABASE",
                    "severity": "ERROR",
                    "transaction_id": extra_id,
                    "message": f"SQL transaction ledger contains {extra_id}, which is not present in the blockchain.",
                })

            projection_fields = {
                "batch_id": "batch_id",
                "actor_id": "actor_id",
                "event_type": "event_type",
                "from_actor": "from_actor",
                "to_actor": "to_actor",
                "from_state": "from_state",
                "to_state": "to_state",
                "quantity_kg": "quantity_kg",
                "record_origin": "record_origin",
                "timestamp": "timestamp",
            }
            for transaction_id in sorted(expected_ids & actual_ids, key=str):
                expected_block_index, expected_tx = expected_transactions[transaction_id]
                row = actual_by_id[transaction_id]
                mismatches = []
                try:
                    block_index_matches = int(row["block_index"]) == int(expected_block_index)
                except (TypeError, ValueError):
                    block_index_matches = False
                if not block_index_matches:
                    mismatches.append("block_index")
                try:
                    stored_json = json.loads(row["transaction_json"])
                    if canonical_json(stored_json) != canonical_json(expected_tx):
                        mismatches.append("transaction_json")
                except (TypeError, ValueError, json.JSONDecodeError):
                    mismatches.append("transaction_json (invalid JSON)")

                for tx_field, db_field in projection_fields.items():
                    expected_value = expected_tx.get(tx_field)
                    stored_value = row[db_field]
                    if tx_field == "quantity_kg" and expected_value is not None and stored_value is not None:
                        try:
                            equal = abs(float(expected_value) - float(stored_value)) <= 1e-9
                        except (TypeError, ValueError):
                            equal = False
                    else:
                        equal = expected_value == stored_value
                    if not equal:
                        mismatches.append(db_field)

                if mismatches:
                    database_issues.append({
                        "code": "LEDGER_RECORD_MISMATCH",
                        "category": "DATABASE",
                        "severity": "ERROR",
                        "transaction_id": transaction_id,
                        "message": (
                            f"SQL ledger record {transaction_id} differs from its blockchain transaction "
                            f"in: {', '.join(sorted(set(mismatches)))}."
                        ),
                    })

            stored_batches = {row["batch_id"]: row for row in batch_rows}
            expected_batch_ids = set(replayed_batches)
            stored_batch_ids = set(stored_batches)
            for missing_id in sorted(expected_batch_ids - stored_batch_ids):
                database_issues.append({
                    "code": "BATCH_ROW_MISSING",
                    "category": "DATABASE",
                    "severity": "ERROR",
                    "message": f"Batch {missing_id} exists in the blockchain history but is missing from the batches table.",
                })
            for extra_id in sorted(stored_batch_ids - expected_batch_ids):
                database_issues.append({
                    "code": "BATCH_ROW_EXTRA",
                    "category": "DATABASE",
                    "severity": "ERROR",
                    "message": f"Batch {extra_id} exists in the batches table but cannot be reconstructed from the blockchain history.",
                })

            batch_fields = ("current_holder", "current_state", "status", "record_origin")
            for batch_id in sorted(expected_batch_ids & stored_batch_ids):
                expected_batch = replayed_batches[batch_id]
                stored_batch = stored_batches[batch_id]
                mismatches = []
                try:
                    quantity_matches = abs(
                        float(expected_batch["quantity_kg"]) - float(stored_batch["quantity_kg"])
                    ) <= 1e-9
                except (TypeError, ValueError):
                    quantity_matches = False
                if not quantity_matches:
                    mismatches.append("quantity_kg")
                for field in batch_fields:
                    if expected_batch.get(field) != stored_batch[field]:
                        mismatches.append(field)
                if mismatches:
                    database_issues.append({
                        "code": "BATCH_STATE_MISMATCH",
                        "category": "DATABASE",
                        "severity": "ERROR",
                        "message": f"Stored batch {batch_id} differs from its blockchain history in: {', '.join(mismatches)}.",
                    })

            expected_edges = {
                (parent_id, child_id)
                for parent_id, info in replayed_lineage.items()
                for child_id in info["children"]
            }
            stored_edges = {
                (row["parent_batch_id"], row["child_batch_id"])
                for row in lineage_rows
            }
            for parent_id, child_id in sorted(expected_edges - stored_edges):
                database_issues.append({
                    "code": "LINEAGE_LINK_MISSING",
                    "category": "DATABASE",
                    "severity": "ERROR",
                    "message": f"Expected lineage link {parent_id} -> {child_id} is missing from SQLite.",
                })
            for parent_id, child_id in sorted(stored_edges - expected_edges):
                database_issues.append({
                    "code": "LINEAGE_LINK_EXTRA",
                    "category": "DATABASE",
                    "severity": "ERROR",
                    "message": f"SQLite contains an unexpected lineage link {parent_id} -> {child_id}.",
                })

            database_result = {
                "checked": True,
                "valid": not database_issues,
                "records_checked": len(database_rows),
                "batches_checked": len(batch_rows),
                "lineage_links_checked": len(lineage_rows),
                "issues": database_issues,
            }
            issues.extend(database_issues)

            actor_registry_issues = []
            stored_actors = {row["actor_id"]: row for row in actor_rows}
            for actor_id, actor in self.actors.items():
                stored_actor = stored_actors.get(actor_id)
                if stored_actor is None:
                    actor_registry_issues.append({
                        "code": "ACTOR_REGISTRY_ENTRY_MISSING",
                        "category": "ACTOR_REGISTRY",
                        "severity": "ERROR",
                        "message": f"Registered actor '{actor_id}' is missing from the SQLite actor registry.",
                    })
                else:
                    expected_role = DEFAULT_ACTORS.get(actor_id)
                    role_policy_mismatch = expected_role is not None and actor["role"] != expected_role
                    stored_registry_mismatch = (
                        stored_actor["role"] != actor["role"]
                        or stored_actor["public_key"] != actor["public_key_pem"]
                    )
                    if role_policy_mismatch or stored_registry_mismatch:
                        actor_registry_issues.append({
                            "code": "ACTOR_REGISTRY_MISMATCH",
                            "category": "ACTOR_REGISTRY",
                            "severity": "ERROR",
                            "message": (
                                f"Stored role or public key for actor '{actor_id}' differs from "
                                "the local key registry or the project's default role policy."
                            ),
                        })
            for extra_actor_id in sorted(set(stored_actors) - set(self.actors), key=str):
                actor_registry_issues.append({
                    "code": "ACTOR_REGISTRY_UNEXPECTED_ENTRY",
                    "category": "ACTOR_REGISTRY",
                    "severity": "ERROR",
                    "message": f"SQLite contains unrecognized participant '{extra_actor_id}'.",
                })
            actor_registry_result = {
                "checked": True,
                "valid": not actor_registry_issues,
                "actors_checked": len(self.actors),
                "issues": actor_registry_issues,
            }
            issues.extend(actor_registry_issues)

        signature_issues = [item for item in issues if item["category"] == "SIGNATURE"]
        permission_issues = [item for item in issues if item["category"] == "PERMISSIONS"]
        transaction_issues = [item for item in issues if item["category"] == "TRANSACTION"]
        signature_result = {
            "valid": not signature_issues,
            "checked": signatures_checked,
            "valid_count": signatures_valid,
            "invalid_count": signatures_checked - signatures_valid,
            "issues": signature_issues,
        }
        permission_result = {
            "valid": not permission_issues,
            "issues": permission_issues,
        }
        transaction_result = {
            "valid": not transaction_issues,
            "issues": transaction_issues,
        }

        return {
            "overall_valid": not issues,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "blocks_checked": chain_result["blocks_checked"],
            "blockchain": chain_result,
            "signatures": signature_result,
            "permissions": permission_result,
            "transaction_structure": transaction_result,
            "database": database_result,
            "actor_registry": actor_registry_result,
            "issues": issues,
        }

    def _validate_signature_and_role(self, tx):
        actor_id = tx.get("actor_id")
        if actor_id not in self.actors:
            return False, "Participant not registered"
        role = self.actors[actor_id]["role"]
        if tx.get("event_type") not in ROLE_PERMISSIONS.get(role, set()):
            return False, "Permission denied"
        if not verify_transaction_signature(tx, self.actors[actor_id]["public_key"]):
            return False, "Invalid digital signature"
        quantity = tx.get("quantity_kg")
        if not isinstance(quantity, (int, float)) or isinstance(quantity, bool) or quantity <= 0:
            return False, "Invalid quantity"
        audit_report = self.audit_chain()
        if not audit_report["overall_valid"] or not self.chain.validate_chain():
            return False, "Blockchain integrity audit failed. No new transaction was recorded."
        return True, "Transaction signature, permission and stored-ledger integrity verified"

    def _append(self, tx):
        self.chain.add_block([tx])
        self.batch_history.setdefault(tx.get("batch_id"), []).append(tx)
        self._save()

    def create_batch(self, actor_id, batch_id, quantity_kg, state, district, harvest_date="", variety="", details=None):
        if actor_id not in self.actors:
            return False, "Participant not registered"
        if self.actors[actor_id]["role"] != "FARMER":
            return False, "Only farmers can create batches"
        if not batch_id or batch_id in self.batches:
            return False, "Batch ID is empty or already exists"
        if not isinstance(quantity_kg, (int, float)) or isinstance(quantity_kg, bool) or quantity_kg <= 0:
            return False, "Quantity must be greater than zero"
        if not state or not district:
            return False, "State and district are required"

        tx = create_transaction(
            self.actors, actor_id, batch_id, "BATCH_CREATED", quantity_kg,
            from_state="", to_state=state,
            details={"crop": "Onion", "district": district, "harvest_date": harvest_date,
                     "variety": variety, **(details or {})},
        )
        ok, message = self._validate_signature_and_role(tx)
        if not ok:
            return False, message

        self.batches[batch_id] = {
            "quantity_kg": float(quantity_kg),
            "current_holder": actor_id,
            "current_state": state,
            "status": "ACTIVE",
            "record_origin": "DEMO",
        }
        self.lineage.setdefault(batch_id, {"parents": [], "children": []})
        self._append(tx)
        return True, "Onion batch created and recorded on blockchain"

    def add_event(self, actor_id, batch_id, event_type, quantity_kg=None,
                  to_state=None, to_actor=None, details=None):
        if batch_id not in self.batches:
            return False, "Batch not found"
        batch = self.batches[batch_id]
        if batch["status"] != "ACTIVE":
            return False, f"Batch is not active (status: {batch['status']})"
        if actor_id != batch["current_holder"]:
            return False, "Participant is not the current batch holder"
        quantity = batch["quantity_kg"] if quantity_kg is None else quantity_kg
        if quantity != batch["quantity_kg"]:
            return False, "Batch quantity mismatch"
        if event_type == "BATCH_CREATED":
            return False, "Use create_batch for batch creation"
        if event_type in {"BATCH_SPLIT", "BATCH_MERGED"}:
            return False, "Use the dedicated split or merge operation"
        if event_type == "OWNERSHIP_TRANSFER":
            if not to_actor or to_actor not in self.actors:
                return False, "Recipient is not registered"
            if to_actor == actor_id:
                return False, "Cannot transfer batch to itself"
            if not to_state:
                return False, "Destination state is required"
        elif event_type == "DELIVERED":
            if not to_state:
                return False, "Destination state is required"
        elif event_type not in {"HARVESTED", "QUALITY_INSPECTED", "PICKED_UP", "RECEIVED", "DISPATCHED"}:
            return False, "Unsupported supply-chain event"

        tx = create_transaction(
            self.actors, actor_id, batch_id, event_type, quantity,
            from_state=batch["current_state"],
            to_state=to_state or batch["current_state"],
            to_actor=to_actor or "",
            details=details,
        )
        ok, message = self._validate_signature_and_role(tx)
        if not ok:
            return False, message

        if event_type == "OWNERSHIP_TRANSFER":
            batch["current_holder"] = to_actor
            batch["current_state"] = to_state
        elif event_type == "DELIVERED":
            batch["current_state"] = to_state
        self._append(tx)
        return True, "Supply-chain event recorded successfully"

    def split_batch(self, actor_id, parent_id, child_batches):
        if parent_id not in self.batches:
            return False, "Parent batch not found"
        parent = self.batches[parent_id]
        if parent["status"] != "ACTIVE":
            return False, "Parent batch is not active"
        if parent["current_holder"] != actor_id:
            return False, "Participant is not the current batch holder"
        if actor_id not in self.actors:
            return False, "Participant not registered"
        if "BATCH_SPLIT" not in ROLE_PERMISSIONS.get(self.actors[actor_id]["role"], set()):
            return False, "Permission denied"
        if not isinstance(child_batches, list) or len(child_batches) < 2:
            return False, "At least two child batches are required"

        seen = set()
        total = 0.0
        for child in child_batches:
            child_id = child.get("batch_id")
            quantity = child.get("quantity_kg")
            if not child_id or child_id in self.batches or child_id in seen:
                return False, "Child batch ID is empty, duplicated or already exists"
            if not isinstance(quantity, (int, float)) or isinstance(quantity, bool) or quantity <= 0:
                return False, "Child quantity must be greater than zero"
            seen.add(child_id)
            total += float(quantity)
        if abs(total - float(parent["quantity_kg"])) > 1e-9:
            return False, "Child quantities do not match parent quantity"

        tx = create_transaction(
            self.actors, actor_id, parent_id, "BATCH_SPLIT", parent["quantity_kg"],
            from_state=parent["current_state"], to_state=parent["current_state"],
            to_actor=actor_id, details={"child_batches": child_batches},
        )
        ok, message = self._validate_signature_and_role(tx)
        if not ok:
            return False, message
        self.chain.add_block([tx])
        parent["status"] = "SPLIT"
        self.lineage.setdefault(parent_id, {"parents": [], "children": []})
        for child in child_batches:
            child_id = child["batch_id"]
            self.batches[child_id] = {
                "quantity_kg": float(child["quantity_kg"]),
                "current_holder": actor_id,
                "current_state": parent["current_state"],
                "status": "ACTIVE",
                "record_origin": "DEMO",
            }
            self.lineage[child_id] = {"parents": [parent_id], "children": []}
            self.lineage[parent_id]["children"].append(child_id)
        self.batch_history.setdefault(parent_id, []).append(tx)
        self._save()
        return True, "Batch split successfully"

    def merge_batches(self, actor_id, parent_ids, new_batch_id):
        if new_batch_id in self.batches:
            return False, "Merged batch ID already exists"
        if not isinstance(parent_ids, list) or len(parent_ids) < 2:
            return False, "At least two parent batches are required"
        if len(parent_ids) != len(set(parent_ids)):
            return False, "Duplicate parent batch IDs"
        if actor_id not in self.actors:
            return False, "Participant not registered"
        if "BATCH_MERGED" not in ROLE_PERMISSIONS.get(self.actors[actor_id]["role"], set()):
            return False, "Permission denied"

        total = 0.0
        location = None
        for parent_id in parent_ids:
            if parent_id not in self.batches:
                return False, f"Parent batch not found: {parent_id}"
            parent = self.batches[parent_id]
            if parent["status"] != "ACTIVE":
                return False, f"Parent batch is not active: {parent_id}"
            if parent["current_holder"] != actor_id:
                return False, "Participant is not the current holder of all parent batches"
            if location is None:
                location = parent["current_state"]
            elif parent["current_state"] != location:
                return False, "All batches must be at the same state/location"
            total += float(parent["quantity_kg"])

        tx = create_transaction(
            self.actors, actor_id, new_batch_id, "BATCH_MERGED", total,
            from_state=location, to_state=location, to_actor=actor_id,
            details={"parent_batches": parent_ids},
        )
        ok, message = self._validate_signature_and_role(tx)
        if not ok:
            return False, message
        self.chain.add_block([tx])
        for parent_id in parent_ids:
            self.batches[parent_id]["status"] = "MERGED"
            self.lineage.setdefault(parent_id, {"parents": [], "children": []})
            self.lineage[parent_id]["children"].append(new_batch_id)
        self.batches[new_batch_id] = {
            "quantity_kg": total,
            "current_holder": actor_id,
            "current_state": location,
            "status": "ACTIVE",
            "record_origin": "DEMO",
        }
        self.lineage[new_batch_id] = {"parents": list(parent_ids), "children": []}
        self.batch_history.setdefault(new_batch_id, []).append(tx)
        self._save()
        return True, "Batches merged successfully"

    def get_batch_history(self, batch_id):
        if batch_id not in self.batches:
            return []
        events = []
        visited = set()

        def collect(current_id):
            if current_id in visited:
                return
            visited.add(current_id)
            for parent_id in self.lineage.get(current_id, {}).get("parents", []):
                collect(parent_id)
            for tx in self.batch_history.get(current_id, []):
                events.append(tx)

        collect(batch_id)
        unique = {tx["transaction_id"]: tx for tx in events}
        return sorted(unique.values(), key=lambda tx: tx.get("timestamp", ""))

    def verify_batch(self, batch_id):
        if batch_id not in self.batches:
            return False, "Batch not found"
        if not self.validate_chain():
            return False, "Blockchain integrity failed"
        history = self.get_batch_history(batch_id)
        if not history:
            return False, "No traceability history found"
        return True, {
            "batch": self.batches[batch_id],
            "lineage": self.lineage.get(batch_id, {"parents": [], "children": []}),
            "history": history,
        }
