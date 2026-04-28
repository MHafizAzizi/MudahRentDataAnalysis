import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from scripts.logger import get_logger

logger = get_logger("load_to_db")

import sqlite3
import pandas as pd
import shutil


CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {config.DB_TABLE} (
    ads_id                TEXT PRIMARY KEY,
    monthly_rent          REAL,
    property_type         TEXT,
    category_id           TEXT,
    CPI                   TEXT,
    state                 TEXT,
    region                TEXT,
    rooms                 TEXT,
    bathroom              TEXT,
    size                  REAL,
    furnished             TEXT,
    facilities            TEXT,
    additional_facilities TEXT,
    body                  TEXT,
    address               TEXT,
    latitude              REAL,
    longitude             REAL,
    publishedDatetime     TEXT,
    scrape_date           TEXT,
    adviewUrl             TEXT
);
"""

CREATE_INDEXES_SQL = [
    f"CREATE INDEX IF NOT EXISTS idx_state ON {config.DB_TABLE}(state);",
    f"CREATE INDEX IF NOT EXISTS idx_cpi ON {config.DB_TABLE}(CPI);",
    f"CREATE INDEX IF NOT EXISTS idx_monthly_rent ON {config.DB_TABLE}(monthly_rent);",
    f"CREATE INDEX IF NOT EXISTS idx_scrape_date ON {config.DB_TABLE}(scrape_date);",
]


def upsert_dataframe(conn: sqlite3.Connection, df: pd.DataFrame) -> int:
    """Insert or replace rows by ads_id. Returns number of rows upserted."""
    if 'ads_id' not in df.columns:
        raise ValueError("DataFrame missing 'ads_id' column — cannot upsert.")

    df = df.drop_duplicates(subset='ads_id')

    # Align columns to DB schema, fill missing with None
    db_cols = [
        'ads_id', 'monthly_rent', 'property_type', 'category_id', 'CPI',
        'state', 'region', 'rooms', 'bathroom', 'size', 'furnished',
        'facilities', 'additional_facilities', 'body', 'address',
        'latitude', 'longitude', 'publishedDatetime', 'scrape_date', 'adviewUrl'
    ]
    for col in db_cols:
        if col not in df.columns:
            df[col] = None
    df = df[db_cols]

    df.to_sql(config.DB_TABLE, conn, if_exists='append', index=False, method='multi')
    return len(df)


def load_processed_files():
    processed_files = list(config.PROCESSED_DATA_DIR.glob('*.csv'))
    if not processed_files:
        logger.warning("No processed CSV files found.")
        return

    conn = sqlite3.connect(config.DB_FILE)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(CREATE_TABLE_SQL)
    for idx_sql in CREATE_INDEXES_SQL:
        conn.execute(idx_sql)

    # Enable upsert via INSERT OR REPLACE by using temp table trick
    # Simpler: use pandas + DELETE existing then INSERT
    total_upserted = 0

    for csv_path in processed_files:
        try:
            df = pd.read_csv(csv_path)
            ads_ids = df['ads_id'].dropna().astype(str).tolist()

            if ads_ids:
                placeholders = ','.join('?' * len(ads_ids))
                conn.execute(
                    f"DELETE FROM {config.DB_TABLE} WHERE ads_id IN ({placeholders})",
                    ads_ids
                )

            count = upsert_dataframe(conn, df)
            conn.commit()

            shutil.move(str(csv_path), str(config.ARCHIVED_DATA_DIR / csv_path.name))

            raw_file = config.RAW_DATA_DIR / csv_path.name
            if raw_file.exists():
                shutil.move(str(raw_file), str(config.OLD_RAW_DIR / csv_path.name))

            logger.info(f"Loaded {count} rows from {csv_path.name} → archived. Raw → old/raw.")
            total_upserted += count

        except Exception as e:
            conn.rollback()
            logger.error(f"Error loading {csv_path.name}: {e}")
            continue

    conn.close()
    logger.info(f"Done. Total rows upserted: {total_upserted}. DB: {config.DB_FILE}")


if __name__ == "__main__":
    load_processed_files()
