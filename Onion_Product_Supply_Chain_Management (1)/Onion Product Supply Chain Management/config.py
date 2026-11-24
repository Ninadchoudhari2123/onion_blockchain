from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "official" / "raw"
PROCESSED_DIR = DATA_DIR / "official" / "processed"
METADATA_DIR = DATA_DIR / "metadata"
KEY_DIR = DATA_DIR / "keys"
DATABASE_DIR = BASE_DIR / "database"
GENERATED_DIR = BASE_DIR / "generated"
QR_DIR = GENERATED_DIR / "qr_codes"

DB_PATH = DATABASE_DIR / "agritrace.db"
RAW_MARKET_FILE = RAW_DIR / "agmarknet_original.csv"
MARKET_FILE = PROCESSED_DIR / "all_india_onion_data.csv"
INVALID_MARKET_FILE = PROCESSED_DIR / "invalid_onion_rows.csv"
METADATA_FILE = METADATA_DIR / "source_metadata.json"

SOURCE_URL = "https://www.data.gov.in/catalog/current-daily-price-various-commodities-various-markets-mandi"
DATASET_NAME = "Current Daily Price of Various Commodities from Various Markets (Mandi)"
PUBLISHER = "Ministry of Agriculture and Farmers Welfare, Government of India"
PRICE_UNIT = "INR per quintal"
