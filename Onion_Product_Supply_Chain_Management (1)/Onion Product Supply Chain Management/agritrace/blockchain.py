import hashlib
import json
from datetime import datetime, timezone


def canonical_json(data):
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


class Block:
    def __init__(self, index, transactions, previous_hash, timestamp=None):
        self.index = int(index)
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        self.transactions = transactions
        self.previous_hash = previous_hash
        self.hash = self.calculate_hash()

    def calculate_hash(self):
        block_data = {
            "index": self.index,
            "timestamp": self.timestamp,
            "transactions": self.transactions,
            "previous_hash": self.previous_hash,
        }
        return hashlib.sha256(canonical_json(block_data).encode("utf-8")).hexdigest()

    def to_dict(self):
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "transactions": self.transactions,
            "previous_hash": self.previous_hash,
            "hash": self.hash,
        }


class Blockchain:
    def __init__(self, blocks=None, create_genesis=True):
        self.chain = list(blocks or [])
        if not self.chain and create_genesis:
            self.create_genesis_block()

    def create_genesis_block(self):
        genesis = Block(0, [{"event": "Genesis Block"}], "0")
        self.chain.append(genesis)
        return genesis

    def add_block(self, transactions):
        if not self.chain:
            self.create_genesis_block()
        previous_block = self.chain[-1]
        new_block = Block(
            len(self.chain),
            transactions,
            previous_block.hash,
        )
        self.chain.append(new_block)
        return new_block

    def validate_chain_detailed(self):
        """Return actionable diagnostics instead of only a True/False result."""
        issues = []
        if not self.chain:
            return {
                "valid": False,
                "blocks_checked": 0,
                "issues": [{
                    "code": "EMPTY_CHAIN",
                    "block_index": None,
                    "message": "No blocks were found in the blockchain.",
                }],
            }

        for position, current_block in enumerate(self.chain):
            if not isinstance(current_block.transactions, list):
                issues.append({
                    "code": "INVALID_TRANSACTION_CONTAINER",
                    "block_index": position,
                    "message": "Block transactions must be stored as a JSON list.",
                })

            if current_block.index != position:
                issues.append({
                    "code": "BLOCK_INDEX_MISMATCH",
                    "block_index": position,
                    "message": (
                        f"Expected block index {position}, "
                        f"but found {current_block.index}. The chain may be reordered "
                        "or a block may be missing."
                    ),
                })

            try:
                calculated_hash = current_block.calculate_hash()
            except Exception as exc:
                calculated_hash = None
                issues.append({
                    "code": "HASH_CALCULATION_ERROR",
                    "block_index": position,
                    "message": f"Could not calculate this block's hash ({type(exc).__name__}).",
                })

            if calculated_hash is not None and current_block.hash != calculated_hash:
                issues.append({
                    "code": "BLOCK_HASH_MISMATCH",
                    "block_index": position,
                    "message": "Block data does not match its stored SHA-256 hash.",
                })

            if position == 0:
                if current_block.previous_hash != "0":
                    issues.append({
                        "code": "GENESIS_LINK_INVALID",
                        "block_index": 0,
                        "message": "The genesis block must use 0 as its previous hash.",
                    })
            else:
                previous_block = self.chain[position - 1]
                if current_block.previous_hash != previous_block.hash:
                    issues.append({
                        "code": "PREVIOUS_HASH_MISMATCH",
                        "block_index": position,
                        "message": (
                            f"Block {position} does not point to the stored hash of "
                            f"block {position - 1}. The chain link is broken."
                        ),
                    })

        return {
            "valid": not issues,
            "blocks_checked": len(self.chain),
            "issues": issues,
        }

    def validate_chain(self):
        """Backward-compatible boolean integrity check."""
        return self.validate_chain_detailed()["valid"]
