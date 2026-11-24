import streamlit as st
import pandas as pd

from .bootstrap import initialize_project
from .database import get_connection
from config import DB_PATH


@st.cache_resource
def get_service():
    return initialize_project()


@st.cache_data(ttl=60)
def load_table(table_name):
    allowed = {
        "actors", "blocks", "chain_transactions", "batches",
        "batch_lineage", "market_prices", "dataset_metadata"
    }
    if table_name not in allowed:
        raise ValueError("Unknown database table")
    with get_connection(DB_PATH) as conn:
        return pd.read_sql_query(f"SELECT * FROM {table_name}", conn)


def refresh_data():
    load_table.clear()
