import json
import sqlite3
from pathlib import Path

from .blockchain import Block

SCHEMA = """
CREATE TABLE IF NOT EXISTS actors (
    actor_id TEXT PRIMARY KEY,
    role TEXT NOT NULL,
    public_key TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS blocks (
    block_index INTEGER PRIMARY KEY,
    timestamp TEXT NOT NULL,
    transactions_json TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    current_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chain_transactions (
    transaction_id TEXT PRIMARY KEY,
    block_index INTEGER NOT NULL,
    batch_id TEXT,
    actor_id TEXT,
    event_type TEXT,
    from_actor TEXT,
    to_actor TEXT,
    from_state TEXT,
    to_state TEXT,
    quantity_kg REAL,
    record_origin TEXT,
    timestamp TEXT,
    transaction_json TEXT NOT NULL,
    FOREIGN KEY (block_index) REFERENCES blocks(block_index)
);
CREATE TABLE IF NOT EXISTS batches (
    batch_id TEXT PRIMARY KEY,
    quantity_kg REAL NOT NULL,
    current_holder TEXT,
    current_state TEXT,
    status TEXT,
    record_origin TEXT NOT NULL DEFAULT 'DEMO',
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS batch_lineage (
    parent_batch_id TEXT NOT NULL,
    child_batch_id TEXT NOT NULL,
    PRIMARY KEY (parent_batch_id, child_batch_id),
    FOREIGN KEY (parent_batch_id) REFERENCES batches(batch_id),
    FOREIGN KEY (child_batch_id) REFERENCES batches(batch_id)
);
CREATE TABLE IF NOT EXISTS market_prices (
    source_row_hash TEXT PRIMARY KEY,
    state TEXT,
    district TEXT,
    market TEXT,
    commodity TEXT,
    variety TEXT,
    grade TEXT,
    arrival_date TEXT,
    min_price REAL,
    max_price REAL,
    modal_price REAL
);
CREATE TABLE IF NOT EXISTS dataset_metadata (
    metadata_id INTEGER PRIMARY KEY,
    dataset_name TEXT,
    publisher TEXT,
    source_url TEXT,
    retrieval_date TEXT,
    first_arrival_date TEXT,
    last_arrival_date TEXT,
    total_records INTEGER,
    description TEXT
);
"""


def get_connection(db_path):
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path):
    with get_connection(db_path) as conn:
        conn.executescript(SCHEMA)


def load_blocks(conn):
    rows = conn.execute(
        "SELECT * FROM blocks ORDER BY block_index"
    ).fetchall()
    blocks = []
    for row in rows:
        try:
            transactions = json.loads(row["transactions_json"])
        except (TypeError, ValueError, json.JSONDecodeError):
            # Preserve a detectable invalid structure instead of crashing the audit.
            transactions = {"_invalid_transactions_json": True}
        try:
            block_index = int(row["block_index"])
        except (TypeError, ValueError):
            block_index = -1
        block = Block(
            index=block_index,
            transactions=transactions,
            previous_hash=row["previous_hash"],
            timestamp=row["timestamp"],
        )
        block.hash = row["current_hash"]
        blocks.append(block)
    return blocks


def load_batches(conn):
    rows = conn.execute("SELECT * FROM batches ORDER BY batch_id").fetchall()
    return {
        row["batch_id"]: {
            "quantity_kg": row["quantity_kg"],
            "current_holder": row["current_holder"],
            "current_state": row["current_state"],
            "status": row["status"],
            "record_origin": row["record_origin"],
        }
        for row in rows
    }


def load_lineage(conn, batches):
    lineage = {
        batch_id: {"parents": [], "children": []}
        for batch_id in batches
    }
    rows = conn.execute("SELECT * FROM batch_lineage").fetchall()
    for row in rows:
        parent_id = row["parent_batch_id"]
        child_id = row["child_batch_id"]
        lineage.setdefault(parent_id, {"parents": [], "children": []})
        lineage.setdefault(child_id, {"parents": [], "children": []})
        if child_id not in lineage[parent_id]["children"]:
            lineage[parent_id]["children"].append(child_id)
        if parent_id not in lineage[child_id]["parents"]:
            lineage[child_id]["parents"].append(parent_id)
    return lineage


def save_service_state(db_path, chain, actors, batches, lineage):
    with get_connection(db_path) as conn:
        for actor_id, actor in actors.items():
            conn.execute(
                """INSERT INTO actors(actor_id, role, public_key, created_at)
                   VALUES (?, ?, ?, COALESCE((SELECT created_at FROM actors WHERE actor_id=?), datetime('now')))
                   ON CONFLICT(actor_id) DO UPDATE SET
                   role=excluded.role, public_key=excluded.public_key""",
                (actor_id, actor["role"], actor["public_key_pem"], actor_id),
            )

        for block in chain.chain:
            transactions_json = json.dumps(
                block.transactions, sort_keys=True, ensure_ascii=False
            )
            conn.execute(
                """INSERT INTO blocks(block_index, timestamp, transactions_json, previous_hash, current_hash)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(block_index) DO UPDATE SET
                   timestamp=excluded.timestamp,
                   transactions_json=excluded.transactions_json,
                   previous_hash=excluded.previous_hash,
                   current_hash=excluded.current_hash""",
                (block.index, block.timestamp, transactions_json,
                 block.previous_hash, block.hash),
            )
            for tx in block.transactions:
                tx_id = tx.get("transaction_id")
                if not tx_id:
                    continue
                conn.execute(
                    """INSERT INTO chain_transactions(
                       transaction_id, block_index, batch_id, actor_id, event_type,
                       from_actor, to_actor, from_state, to_state, quantity_kg,
                       record_origin, timestamp, transaction_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(transaction_id) DO UPDATE SET
                       block_index=excluded.block_index,
                       transaction_json=excluded.transaction_json""",
                    (str(tx_id), block.index, tx.get("batch_id"), tx.get("actor_id"),
                     tx.get("event_type"), tx.get("from_actor"), tx.get("to_actor"),
                     tx.get("from_state"), tx.get("to_state"), tx.get("quantity_kg"),
                     tx.get("record_origin", "DEMO"), tx.get("timestamp"),
                     json.dumps(tx, sort_keys=True, ensure_ascii=False)),
                )

        for batch_id, batch in batches.items():
            conn.execute(
                """INSERT INTO batches(batch_id, quantity_kg, current_holder, current_state,
                   status, record_origin, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                   ON CONFLICT(batch_id) DO UPDATE SET
                   quantity_kg=excluded.quantity_kg,
                   current_holder=excluded.current_holder,
                   current_state=excluded.current_state,
                   status=excluded.status,
                   record_origin=excluded.record_origin,
                   updated_at=excluded.updated_at""",
                (batch_id, batch["quantity_kg"], batch.get("current_holder"),
                 batch.get("current_state"), batch.get("status"),
                 batch.get("record_origin", "DEMO")),
            )

        conn.execute("DELETE FROM batch_lineage")
        links = set()
        for batch_id, info in lineage.items():
            for parent_id in info.get("parents", []):
                links.add((parent_id, batch_id))
            for child_id in info.get("children", []):
                links.add((batch_id, child_id))
        for parent_id, child_id in sorted(links):
            if parent_id in batches and child_id in batches:
                conn.execute(
                    "INSERT OR IGNORE INTO batch_lineage(parent_batch_id, child_batch_id) VALUES (?, ?)",
                    (parent_id, child_id),
                )


def import_market_rows(db_path, market_df):
    import hashlib
    import pandas as pd

    columns = [
        "state", "district", "market", "commodity", "variety", "grade",
        "arrival_date", "min_price", "max_price", "modal_price"
    ]
    missing = [col for col in columns if col not in market_df.columns]
    if missing:
        raise ValueError(f"Market dataset is missing columns: {missing}")

    inserted = 0
    with get_connection(db_path) as conn:
        for row in market_df[columns].to_dict("records"):
            clean_row = {}
            for col in columns:
                value = row[col]
                if pd.isna(value):
                    value = None
                elif col in {"min_price", "max_price", "modal_price"}:
                    value = float(value)
                else:
                    value = str(value)
                clean_row[col] = value
            row_text = json.dumps(clean_row, sort_keys=True, ensure_ascii=False)
            row_hash = hashlib.sha256(row_text.encode("utf-8")).hexdigest()
            result = conn.execute(
                """INSERT OR IGNORE INTO market_prices(
                   source_row_hash, state, district, market, commodity, variety,
                   grade, arrival_date, min_price, max_price, modal_price)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (row_hash, clean_row["state"], clean_row["district"],
                 clean_row["market"], clean_row["commodity"], clean_row["variety"],
                 clean_row["grade"], clean_row["arrival_date"], clean_row["min_price"],
                 clean_row["max_price"], clean_row["modal_price"]),
            )
            inserted += result.rowcount
    return inserted


def save_dataset_metadata(db_path, metadata):
    with get_connection(db_path) as conn:
        conn.execute(
            """INSERT INTO dataset_metadata(
               metadata_id, dataset_name, publisher, source_url, retrieval_date,
               first_arrival_date, last_arrival_date, total_records, description)
               VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(metadata_id) DO UPDATE SET
               dataset_name=excluded.dataset_name, publisher=excluded.publisher,
               source_url=excluded.source_url, retrieval_date=excluded.retrieval_date,
               first_arrival_date=excluded.first_arrival_date,
               last_arrival_date=excluded.last_arrival_date,
               total_records=excluded.total_records, description=excluded.description""",
            (metadata["dataset_name"], metadata["publisher"], metadata["source_url"],
             metadata["retrieval_date"], metadata["first_arrival_date"],
             metadata["last_arrival_date"], metadata.get("total_records", metadata.get("clean_onion_rows", 0)),
             metadata.get("description", metadata.get("record_type", "") + " " + metadata.get("period_limitation", ""))),
        )
