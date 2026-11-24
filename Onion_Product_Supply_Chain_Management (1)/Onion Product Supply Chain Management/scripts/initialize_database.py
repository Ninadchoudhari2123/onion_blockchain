import sys
from pathlib import Path

base_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(base_dir))

from agritrace.bootstrap import initialize_project
from config import DB_PATH

if __name__ == "__main__":
    service = initialize_project()
    print("Database initialized:", DB_PATH)
    print("Blocks:", len(service.chain.chain))
    print("Batches:", len(service.batches))
    print("Blockchain valid:", service.validate_chain())
