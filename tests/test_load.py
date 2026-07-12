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
        # Re-upsert ads_id '001' with a new rent — ON CONFLICT updates in place.
        updated = pd.DataFrame({'ads_id': ['001'], 'monthly_rent': [1500.0]})
        load_module.upsert_dataframe(in_memory_conn, updated)
        in_memory_conn.commit()
        result = pd.read_sql("SELECT * FROM properties WHERE ads_id = '001'", in_memory_conn)
        assert len(result) == 1
        assert result['monthly_rent'].iloc[0] == 1500.0

    def test_insert_sets_recheck_defaults(self, load_module, in_memory_conn):
        df = pd.DataFrame({'ads_id': ['010'], 'scrape_date': ['2026-05-01']})
        load_module.upsert_dataframe(in_memory_conn, df)
        row = pd.read_sql("SELECT * FROM properties WHERE ads_id = '010'", in_memory_conn).iloc[0]
        assert row['first_seen'] == '2026-05-01'
        assert row['availability_status'] == 'active'
        assert row['check_count'] == 0

    def test_upsert_preserves_recheck_state(self, load_module, in_memory_conn):
        df = pd.DataFrame({'ads_id': ['020'], 'scrape_date': ['2026-05-01'], 'monthly_rent': [1000.0]})
        load_module.upsert_dataframe(in_memory_conn, df)
        in_memory_conn.commit()
        # Simulate recheck having marked it gone and bumped check_count.
        in_memory_conn.execute(
            "UPDATE properties SET availability_status='rented', gone_at='2026-05-10', "
            "check_count=5, last_checked_at='2026-05-10' WHERE ads_id='020'"
        )
        in_memory_conn.commit()
        # Re-scrape later: listing reappears -> re-affirmed active, first_seen/check_count kept.
        df2 = pd.DataFrame({'ads_id': ['020'], 'scrape_date': ['2026-05-20'], 'monthly_rent': [1100.0]})
        load_module.upsert_dataframe(in_memory_conn, df2)
        in_memory_conn.commit()
        row = pd.read_sql("SELECT * FROM properties WHERE ads_id='020'", in_memory_conn).iloc[0]
        assert row['first_seen'] == '2026-05-01'        # preserved
        assert row['check_count'] == 5                  # preserved
        assert row['availability_status'] == 'active'   # re-affirmed live
        assert row['gone_at'] is None                   # cleared
        assert row['last_checked_at'] == '2026-05-20'   # bumped to new scrape
        assert row['monthly_rent'] == 1100.0            # scrape col refreshed

    def test_missing_ads_id_raises(self, load_module, in_memory_conn):
        bad_df = pd.DataFrame({'state': ['Selangor'], 'monthly_rent': [1000.0]})
        with pytest.raises(ValueError, match="ads_id"):
            load_module.upsert_dataframe(in_memory_conn, bad_df)

    def test_missing_columns_filled_with_none(self, load_module, in_memory_conn):
        minimal_df = pd.DataFrame({'ads_id': ['999'], 'monthly_rent': [1000.0]})
        count = load_module.upsert_dataframe(in_memory_conn, minimal_df)
        assert count == 1
