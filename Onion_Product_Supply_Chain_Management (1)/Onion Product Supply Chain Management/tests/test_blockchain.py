from agritrace.blockchain import Block, Blockchain


def test_genesis_block_is_valid():
    chain = Blockchain()
    assert len(chain.chain) == 1
    assert chain.validate_chain() is True


def test_added_block_is_valid():
    chain = Blockchain()
    chain.add_block([{"event": "HARVESTED", "quantity_kg": 1000}])
    assert len(chain.chain) == 2
    assert chain.validate_chain() is True


def test_tampering_is_detected():
    chain = Blockchain()
    chain.add_block([{"event": "HARVESTED", "quantity_kg": 1000}])
    chain.chain[1].transactions[0]["quantity_kg"] = 500
    assert chain.validate_chain() is False


def test_detailed_validation_reports_a_hash_mismatch():
    chain = Blockchain()
    chain.add_block([{"event": "HARVESTED", "quantity_kg": 1000}])
    chain.chain[1].transactions[0]["quantity_kg"] = 500

    report = chain.validate_chain_detailed()

    assert report["valid"] is False
    assert report["blocks_checked"] == 2
    assert any(issue["code"] == "BLOCK_HASH_MISMATCH" for issue in report["issues"])


def test_empty_stored_chain_is_not_replaced_with_a_genesis_block():
    chain = Blockchain([], create_genesis=False)
    report = chain.validate_chain_detailed()

    assert report["valid"] is False
    assert report["issues"][0]["code"] == "EMPTY_CHAIN"
