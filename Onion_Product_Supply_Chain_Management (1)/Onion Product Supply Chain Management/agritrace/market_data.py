import hashlib
import json
from datetime import date
from pathlib import Path

import pandas as pd

from config import (
    DATASET_NAME, PUBLISHER, SOURCE_URL, PRICE_UNIT,
    RAW_MARKET_FILE, MARKET_FILE, INVALID_MARKET_FILE, METADATA_FILE,
)
from .database import import_market_rows, save_dataset_metadata

COLUMN_MAP = {
    "min_x0020_price": "min_price",
    "max_x0020_price": "max_price",
    "modal_x0020_price": "modal_price",
}


def standardize_columns(df):
    df = df.copy()
    df.columns = [str(col).strip().lower().replace(" ", "_") for col in df.columns]
    renamed = {}
    for old, new in COLUMN_MAP.items():
        if old in df.columns:
            renamed[old] = new
    return df.rename(columns=renamed)


def prepare_market_data(raw_file=RAW_MARKET_FILE, output_file=MARKET_FILE):
    raw_file = Path(raw_file)
    output_file = Path(output_file)
    if not raw_file.exists():
        raise FileNotFoundError(f"Original AGMARKNET file not found: {raw_file}")

    if raw_file.suffix.lower() in {".xlsx", ".xls"}:
        df = pd.read_excel(raw_file)
    else:
        df = pd.read_csv(raw_file)

    df = standardize_columns(df)
    required = [
        "state", "district", "market", "commodity", "variety", "grade",
        "arrival_date", "min_price", "max_price", "modal_price"
    ]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Original dataset is missing columns: {missing}")

    for col in ["state", "district", "market", "commodity", "variety", "grade"]:
        df[col] = df[col].astype("string").str.strip()

    df["arrival_date"] = pd.to_datetime(df["arrival_date"], dayfirst=True, errors="coerce")
    for col in ["min_price", "max_price", "modal_price"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    onion_df = df[df["commodity"].str.casefold() == "onion"].copy()
    onion_df = onion_df[required].drop_duplicates().copy()

    required_values = ["state", "district", "market", "arrival_date", "min_price", "max_price", "modal_price"]
    missing_rows = onion_df[onion_df[required_values].isna().any(axis=1)].copy()
    clean_df = onion_df.dropna(subset=required_values).copy()

    valid_mask = (
        (clean_df["min_price"] >= 0)
        & (clean_df["max_price"] >= clean_df["min_price"])
        & (clean_df["modal_price"] >= clean_df["min_price"])
        & (clean_df["modal_price"] <= clean_df["max_price"])
    )
    invalid_price_rows = clean_df[~valid_mask].copy()
    clean_df = clean_df[valid_mask].copy()

    invalid_df = pd.concat([missing_rows, invalid_price_rows], ignore_index=True)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    INVALID_MARKET_FILE.parent.mkdir(parents=True, exist_ok=True)
    clean_df.to_csv(output_file, index=False)
    invalid_df.to_csv(INVALID_MARKET_FILE, index=False)

    source_hash = hashlib.sha256(raw_file.read_bytes()).hexdigest()
    metadata = {
        "dataset_name": DATASET_NAME,
        "publisher": PUBLISHER,
        "source_url": SOURCE_URL,
        "retrieval_date": date.today().isoformat(),
        "first_arrival_date": clean_df["arrival_date"].min().date().isoformat() if not clean_df.empty else None,
        "last_arrival_date": clean_df["arrival_date"].max().date().isoformat() if not clean_df.empty else None,
        "total_source_rows": int(len(df)),
        "onion_rows_before_validation": int(len(onion_df)),
        "clean_onion_rows": int(len(clean_df)),
        "excluded_rows": int(len(invalid_df)),
        "states": int(clean_df["state"].nunique()),
        "districts": int(clean_df["district"].nunique()),
        "markets": int(clean_df["market"].nunique()),
        "price_unit": PRICE_UNIT,
        "source_file": raw_file.name,
        "source_file_sha256": source_hash,
        "period_limitation": "Only the arrival dates present in the downloaded source file are represented. This snapshot is not a 12-month historical series unless the source file contains that date range.",
        "record_type": "Real government market-price observations; not batch-level traceability events.",
    }
    METADATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    METADATA_FILE.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return clean_df, invalid_df, metadata


def import_market_file(db_path, market_file=MARKET_FILE):
    market_file = Path(market_file)
    if not market_file.exists():
        clean_df, _, metadata = prepare_market_data()
    else:
        clean_df = pd.read_csv(market_file)
        if "arrival_date" in clean_df.columns:
            clean_df["arrival_date"] = pd.to_datetime(clean_df["arrival_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        metadata = json.loads(METADATA_FILE.read_text(encoding="utf-8")) if METADATA_FILE.exists() else None

    inserted = import_market_rows(db_path, clean_df)
    if metadata:
        save_dataset_metadata(db_path, metadata)
    return inserted
