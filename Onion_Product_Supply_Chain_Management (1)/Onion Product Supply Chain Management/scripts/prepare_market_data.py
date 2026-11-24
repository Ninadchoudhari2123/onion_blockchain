import sys
from pathlib import Path

base_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(base_dir))

from agritrace.market_data import prepare_market_data

if __name__ == "__main__":
    clean_df, invalid_df, metadata = prepare_market_data()
    print("Original source:", metadata["source_file"])
    print("Clean onion records:", len(clean_df))
    print("Excluded rows for review:", len(invalid_df))
    print("States:", clean_df["state"].nunique())
    print("Districts:", clean_df["district"].nunique())
    print("Markets:", clean_df["market"].nunique())
    print("Date coverage:", metadata["first_arrival_date"], "to", metadata["last_arrival_date"])
    print("Saved:", base_dir / "data" / "official" / "processed" / "all_india_onion_data.csv")
