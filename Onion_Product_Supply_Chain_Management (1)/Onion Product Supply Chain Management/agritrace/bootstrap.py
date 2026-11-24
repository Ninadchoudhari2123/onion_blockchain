import json
from pathlib import Path

import pandas as pd

from config import (
    DB_PATH, KEY_DIR, MARKET_FILE, RAW_MARKET_FILE, METADATA_FILE,
)
from .database import get_connection, import_market_rows, init_db, save_dataset_metadata
from .market_data import prepare_market_data
from .service import AgriTraceService


def get_service():
    init_db(DB_PATH)
    return AgriTraceService(DB_PATH, KEY_DIR)


def initialize_project():
    init_db(DB_PATH)
    if not MARKET_FILE.exists() and RAW_MARKET_FILE.exists():
        prepare_market_data(RAW_MARKET_FILE, MARKET_FILE)
    if MARKET_FILE.exists():
        market_df = pd.read_csv(MARKET_FILE)
        import_market_rows(DB_PATH, market_df)
        if METADATA_FILE.exists():
            metadata = json.loads(METADATA_FILE.read_text(encoding="utf-8"))
            save_dataset_metadata(DB_PATH, metadata)
    service = get_service()
    return service


def load_table(table_name):
    allowed = {
        "actors", "blocks", "chain_transactions", "batches",
        "batch_lineage", "market_prices", "dataset_metadata"
    }
    if table_name not in allowed:
        raise ValueError("Unknown database table")
    with get_connection(DB_PATH) as conn:
        return pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
