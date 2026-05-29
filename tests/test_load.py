import sqlite3
import pandas as pd
import pytest


@pytest.fixture
def in_memory_conn(load_module):
    """SQLite in-memory connection with properties table, schema from the module."""
    conn = sqlite3.connect(":memory:")
    conn.execute(load_module.CREATE_TABLE_SQL)
    conn.commit()
    return conn


@pytest.fixture
def sample_df():
    return pd.DataFrame({
        'ads_id': ['001', '002', '003'],
        'monthly_rent': [1200.0, 2500.0, 800.0],
        'state': ['Selangor', 'KL', 'Penang'],
        'CPI': ['Apartment', 'Condominium', 'Apartment'],
        'property_type': ['Apartment', 'Condominium', 'Flat'],
    })


class TestUpsertDataframe:
    def test_inserts_rows(self, load_module, in_memory_conn, sample_df):
        count = load_module.upsert_dataframe(in_memory_conn, sample_df)
        assert count == 3

    def test_rows_in_db(self, load_module, in_memory_conn, sample_df):
        load_module.upsert_dataframe(in_memory_conn, sample_df)
        result = pd.read_sql("SELECT * FROM properties", in_memory_conn)
        assert len(result) == 3

    def test_upsert_replaces_existing(self, load_module, in_memory_conn, sample_df):
        load_module.upsert_dataframe(in_memory_conn, sample_df)
        in_memory_conn.commit()
        # Update rent for ads_id '001'
        updated = pd.DataFrame({'ads_id': ['001'], 'monthly_rent': [1500.0]})
        in_memory_conn.execute("DELETE FROM properties WHERE ads_id IN ('001')")
        load_module.upsert_dataframe(in_memory_conn, updated)
        in_memory_conn.commit()
        result = pd.read_sql("SELECT * FROM properties WHERE ads_id = '001'", in_memory_conn)
        assert len(result) == 1
        assert result['monthly_rent'].iloc[0] == 1500.0

    def test_missing_ads_id_raises(self, load_module, in_memory_conn):
        bad_df = pd.DataFrame({'state': ['Selangor'], 'monthly_rent': [1000.0]})
        with pytest.raises(ValueError, match="ads_id"):
            load_module.upsert_dataframe(in_memory_conn, bad_df)

    def test_missing_columns_filled_with_none(self, load_module, in_memory_conn):
        minimal_df = pd.DataFrame({'ads_id': ['999'], 'monthly_rent': [1000.0]})
        count = load_module.upsert_dataframe(in_memory_conn, minimal_df)
        assert count == 1
