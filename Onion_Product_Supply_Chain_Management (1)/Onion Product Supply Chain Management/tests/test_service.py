from agritrace.service import AgriTraceService


def test_create_transfer_split_and_merge(tmp_path):
    service = AgriTraceService(tmp_path / "test.db", tmp_path / "keys")

    ok, message = service.create_batch(
        "farmer_001", "TEST-001", 1000, "Maharashtra", "Nashik", "2026-11-19"
    )
    assert ok, message

    ok, message = service.add_event(
        "farmer_001", "TEST-001", "OWNERSHIP_TRANSFER",
        to_state="Maharashtra", to_actor="center_001"
    )
    assert ok, message

    ok, message = service.split_batch(
        "center_001", "TEST-001",
        [
            {"batch_id": "TEST-001-A", "quantity_kg": 600},
            {"batch_id": "TEST-001-B", "quantity_kg": 400},
        ],
    )
    assert ok, message
    assert service.batches["TEST-001"]["status"] == "SPLIT"

    ok, message = service.merge_batches(
        "center_001", ["TEST-001-A", "TEST-001-B"], "TEST-001-M"
    )
    assert ok, message
    assert service.batches["TEST-001-M"]["quantity_kg"] == 1000
    assert service.validate_chain() is True


def test_unauthorized_role_is_rejected(tmp_path):
    service = AgriTraceService(tmp_path / "test.db", tmp_path / "keys")
    ok, message = service.create_batch(
        "retailer_001", "TEST-002", 100, "Delhi", "Delhi"
    )
    assert ok is False
    assert "Only farmers" in message


def test_service_persists_and_reloads(tmp_path):
    db_path = tmp_path / "agritrace.db"
    key_dir = tmp_path / "keys"

    first = AgriTraceService(db_path, key_dir)
    ok, message = first.create_batch(
        "farmer_001", "PERSIST-001", 250, "Maharashtra", "Nashik"
    )
    assert ok, message

    second = AgriTraceService(db_path, key_dir)
    assert second.validate_chain() is True
    assert "PERSIST-001" in second.batches
    assert second.batches["PERSIST-001"]["quantity_kg"] == 250
    assert len(second.chain.chain) == 2


def test_farmer_current_holder_can_split_and_merge(tmp_path):
    service = AgriTraceService(tmp_path / "farmer_split.db", tmp_path / "keys")

    ok, message = service.create_batch(
        "farmer_001", "FARMER-SPLIT-001", 1000,
        "Maharashtra", "Nashik", "2026-11-23"
    )
    assert ok, message

    # The farmer is still the current holder immediately after creating the batch.
    ok, message = service.split_batch(
        "farmer_001",
        "FARMER-SPLIT-001",
        [
            {"batch_id": "FARMER-SPLIT-001-A", "quantity_kg": 600},
            {"batch_id": "FARMER-SPLIT-001-B", "quantity_kg": 400},
        ],
    )
    assert ok, message
    assert service.batches["FARMER-SPLIT-001"]["status"] == "SPLIT"

    ok, message = service.merge_batches(
        "farmer_001",
        ["FARMER-SPLIT-001-A", "FARMER-SPLIT-001-B"],
        "FARMER-SPLIT-001-M",
    )
    assert ok, message
    assert service.batches["FARMER-SPLIT-001-M"]["quantity_kg"] == 1000
    assert service.batches["FARMER-SPLIT-001-M"]["current_holder"] == "farmer_001"
    assert service.validate_chain() is True


def test_transporter_cannot_split_even_when_current_holder(tmp_path):
    service = AgriTraceService(tmp_path / "transporter_split.db", tmp_path / "keys")

    ok, message = service.create_batch(
        "farmer_001", "TRANSPORTER-SPLIT-001", 1000,
        "Maharashtra", "Nashik", "2026-11-23"
    )
    assert ok, message

    ok, message = service.add_event(
        "farmer_001",
        "TRANSPORTER-SPLIT-001",
        "OWNERSHIP_TRANSFER",
        to_state="Maharashtra",
        to_actor="transporter_001",
    )
    assert ok, message

    ok, message = service.split_batch(
        "transporter_001",
        "TRANSPORTER-SPLIT-001",
        [
            {"batch_id": "TRANSPORTER-SPLIT-001-A", "quantity_kg": 500},
            {"batch_id": "TRANSPORTER-SPLIT-001-B", "quantity_kg": 500},
        ],
    )
    assert ok is False
    assert message == "Permission denied"
    assert service.batches["TRANSPORTER-SPLIT-001"]["status"] == "ACTIVE"
    assert service.validate_chain() is True


def test_full_audit_passes_for_a_valid_persisted_chain(tmp_path):
    service = AgriTraceService(tmp_path / "audit_valid.db", tmp_path / "keys")
    ok, message = service.create_batch(
        "farmer_001", "AUDIT-VALID-001", 500, "Maharashtra", "Nashik"
    )
    assert ok, message

    report = service.audit_chain()

    assert report["overall_valid"] is True
    assert report["blockchain"]["valid"] is True
    assert report["signatures"]["valid"] is True
    assert report["database"]["valid"] is True
    assert report["actor_registry"]["valid"] is True


def test_signature_detects_payload_tampering_after_hashes_are_rebuilt(tmp_path):
    import copy

    service = AgriTraceService(tmp_path / "audit_signature.db", tmp_path / "keys")
    ok, message = service.create_batch(
        "farmer_001", "AUDIT-SIGNATURE-001", 500, "Maharashtra", "Nashik"
    )
    assert ok, message

    test_chain = copy.deepcopy(service.get_persisted_chain())
    test_chain.chain[1].transactions[0]["quantity_kg"] = 501.0
    for index in range(1, len(test_chain.chain)):
        if index > 1:
            test_chain.chain[index].previous_hash = test_chain.chain[index - 1].hash
        test_chain.chain[index].hash = test_chain.chain[index].calculate_hash()

    report = service.audit_chain(chain_override=test_chain)

    assert report["blockchain"]["valid"] is True
    assert report["signatures"]["valid"] is False
    assert any(issue["code"] == "INVALID_TRANSACTION_SIGNATURE" for issue in report["issues"])


def test_audit_detects_sql_transaction_ledger_tampering(tmp_path):
    from agritrace.database import get_connection

    db_path = tmp_path / "audit_database.db"
    service = AgriTraceService(db_path, tmp_path / "keys")
    ok, message = service.create_batch(
        "farmer_001", "AUDIT-DATABASE-001", 500, "Maharashtra", "Nashik"
    )
    assert ok, message

    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE chain_transactions SET quantity_kg = 999 "
            "WHERE batch_id = ?",
            ("AUDIT-DATABASE-001",),
        )

    report = service.audit_chain()

    assert report["overall_valid"] is False
    assert report["database"]["valid"] is False
    assert any(issue["code"] == "LEDGER_RECORD_MISMATCH" for issue in report["issues"])


def test_new_transactions_are_blocked_when_sql_ledger_has_been_tampered(tmp_path):
    from agritrace.database import get_connection

    db_path = tmp_path / "audit_write_protection.db"
    service = AgriTraceService(db_path, tmp_path / "keys")
    ok, message = service.create_batch(
        "farmer_001", "AUDIT-WRITE-GUARD-001", 500, "Maharashtra", "Nashik"
    )
    assert ok, message

    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE chain_transactions SET quantity_kg = 999 WHERE batch_id = ?",
            ("AUDIT-WRITE-GUARD-001",),
        )

    ok, message = service.create_batch(
        "farmer_001", "AUDIT-WRITE-GUARD-002", 300, "Maharashtra", "Pune"
    )

    assert ok is False
    assert "integrity audit failed" in message.lower()
    assert "AUDIT-WRITE-GUARD-002" not in service.batches


def test_audit_detects_batch_snapshot_tampering(tmp_path):
    from agritrace.database import get_connection

    db_path = tmp_path / "audit_batch_snapshot.db"
    service = AgriTraceService(db_path, tmp_path / "keys")
    ok, message = service.create_batch(
        "farmer_001", "AUDIT-BATCH-001", 1000, "Maharashtra", "Nashik"
    )
    assert ok, message
    ok, message = service.split_batch(
        "farmer_001", "AUDIT-BATCH-001", [
            {"batch_id": "AUDIT-BATCH-001-A", "quantity_kg": 600},
            {"batch_id": "AUDIT-BATCH-001-B", "quantity_kg": 400},
        ]
    )
    assert ok, message

    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE batches SET quantity_kg = 601 WHERE batch_id = ?",
            ("AUDIT-BATCH-001-A",),
        )

    report = service.audit_chain()

    assert report["overall_valid"] is False
    assert any(issue["code"] == "BATCH_STATE_MISMATCH" for issue in report["issues"])


def test_audit_detects_lineage_link_deletion(tmp_path):
    from agritrace.database import get_connection

    db_path = tmp_path / "audit_lineage.db"
    service = AgriTraceService(db_path, tmp_path / "keys")
    ok, message = service.create_batch(
        "farmer_001", "AUDIT-LINEAGE-001", 1000, "Maharashtra", "Nashik"
    )
    assert ok, message
    ok, message = service.split_batch(
        "farmer_001", "AUDIT-LINEAGE-001", [
            {"batch_id": "AUDIT-LINEAGE-001-A", "quantity_kg": 600},
            {"batch_id": "AUDIT-LINEAGE-001-B", "quantity_kg": 400},
        ]
    )
    assert ok, message

    with get_connection(db_path) as conn:
        conn.execute(
            "DELETE FROM batch_lineage WHERE parent_batch_id = ? AND child_batch_id = ?",
            ("AUDIT-LINEAGE-001", "AUDIT-LINEAGE-001-A"),
        )

    report = service.audit_chain()

    assert report["overall_valid"] is False
    assert any(issue["code"] == "LINEAGE_LINK_MISSING" for issue in report["issues"])


def test_audit_reports_malformed_block_json_without_crashing(tmp_path):
    from agritrace.database import get_connection

    db_path = tmp_path / "audit_malformed_block_json.db"
    service = AgriTraceService(db_path, tmp_path / "keys")

    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE blocks SET transactions_json = 'not-valid-json' WHERE block_index = 0"
        )

    report = service.audit_chain()

    assert report["overall_valid"] is False
    assert any(issue["code"] == "INVALID_TRANSACTION_CONTAINER" for issue in report["issues"])
