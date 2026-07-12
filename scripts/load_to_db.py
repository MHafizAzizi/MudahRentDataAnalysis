import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from scripts.logger import get_logger

logger = get_logger("load_to_db")

import sqlite3
import pandas as pd


CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {config.DB_TABLE} (
    ads_id                TEXT PRIMARY KEY,
    monthly_rent          REAL,
    property_type         TEXT,
    property_type_id      TEXT,
    category_id           TEXT,
    CPI                   TEXT,
    state                 TEXT,
    region                TEXT,
    subarea_id            TEXT,
    rooms                 TEXT,
    bathroom              TEXT,
    size                  REAL,
    address               TEXT,
    seller_name           TEXT,
    company_ad            TEXT,
    ad_seller_type        TEXT,
    store_verified        TEXT,
    ad_expiry             TEXT,
    latitude              REAL,
    longitude             REAL,
    publishedDatetime     TEXT,
    scrape_date           TEXT,
    adviewUrl             TEXT,
    first_seen            TEXT,
    last_checked_at       TEXT,
    availability_status   TEXT DEFAULT 'active',
    gone_at               TEXT,
    check_count           INTEGER DEFAULT 0
);
"""

# Full column spec (excluding ads_id PK), in CREATE_TABLE order. Drives the schema
# migration for pre-existing DBs (ensure_schema).
COLUMN_DEFS = {
    "monthly_rent": "REAL",
    "property_type": "TEXT",
    "property_type_id": "TEXT",
    "category_id": "TEXT",
    "CPI": "TEXT",
    "state": "TEXT",
    "region": "TEXT",
    "subarea_id": "TEXT",
    "rooms": "TEXT",
    "bathroom": "TEXT",
    "size": "REAL",
    "address": "TEXT",
    "seller_name": "TEXT",
    "company_ad": "TEXT",
    "ad_seller_type": "TEXT",
    "store_verified": "TEXT",
    "ad_expiry": "TEXT",
    "latitude": "REAL",
    "longitude": "REAL",
    "publishedDatetime": "TEXT",
    "scrape_date": "TEXT",
    "adviewUrl": "TEXT",
    # Recheck-managed columns (maintained by scripts/recheck.py).
    "first_seen": "TEXT",
    "last_checked_at": "TEXT",
    "availability_status": "TEXT DEFAULT 'active'",
    "gone_at": "TEXT",
    "check_count": "INTEGER DEFAULT 0",
}

# Recheck-managed columns — kept out of the scrape upsert to preserve availability history.
RECHECK_COLUMNS = {"first_seen", "last_checked_at", "availability_status", "gone_at", "check_count"}

# Scrape-sourced columns, in order — the only columns the upsert writes.
SCRAPE_COLUMNS = ['ads_id'] + [c for c in COLUMN_DEFS if c not in RECHECK_COLUMNS]

CREATE_INDEXES_SQL = [
    f"CREATE INDEX IF NOT EXISTS idx_state ON {config.DB_TABLE}(state);",
    f"CREATE INDEX IF NOT EXISTS idx_cpi ON {config.DB_TABLE}(CPI);",
    f"CREATE INDEX IF NOT EXISTS idx_monthly_rent ON {config.DB_TABLE}(monthly_rent);",
    f"CREATE INDEX IF NOT EXISTS idx_scrape_date ON {config.DB_TABLE}(scrape_date);",
    f"CREATE INDEX IF NOT EXISTS idx_ad_expiry ON {config.DB_TABLE}(ad_expiry);",
    f"CREATE INDEX IF NOT EXISTS idx_property_type_id ON {config.DB_TABLE}(property_type_id);",
    f"CREATE INDEX IF NOT EXISTS idx_availability_status ON {config.DB_TABLE}(availability_status);",
]

# Columns used for content-deduplication (same listing posted multiple times).
_DEDUP_COLS = "monthly_rent, property_type, state, region, rooms, bathroom, size, address, publishedDatetime"


def _dedup(conn: sqlite3.Connection) -> int:
    """Delete content-duplicate rows, keeping the lowest ads_id per group. Returns rows deleted."""
    cur = conn.execute(f"""
        DELETE FROM {config.DB_TABLE}
        WHERE ads_id NOT IN (
            SELECT MIN(ads_id)
            FROM {config.DB_TABLE}
            GROUP BY {_DEDUP_COLS}
        )
    """)
    conn.commit()
    return cur.rowcount


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Add any missing columns to an existing table, then seed recheck defaults.

    Idempotent: safe to call on every load/recheck run. Fresh DBs already have all
    columns via CREATE_TABLE_SQL; this migrates DBs created with an older schema
    (e.g. before the scrape-field expansion or the recheck feature).
    """
    conn.execute(CREATE_TABLE_SQL)  # no-op if table exists; creates it otherwise
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({config.DB_TABLE})")}
    added = [c for c in COLUMN_DEFS if c not in existing]
    for col in added:
        conn.execute(f"ALTER TABLE {config.DB_TABLE} ADD COLUMN {col} {COLUMN_DEFS[col]};")

    if any(c in RECHECK_COLUMNS for c in added):
        # Seed pre-existing rows: treat already-scraped listings as active,
        # first seen on their scrape_date.
        conn.execute(
            f"UPDATE {config.DB_TABLE} SET first_seen = scrape_date WHERE first_seen IS NULL;"
        )
        conn.execute(
            f"UPDATE {config.DB_TABLE} SET availability_status = 'active' "
            f"WHERE availability_status IS NULL;"
        )
        conn.execute(
            f"UPDATE {config.DB_TABLE} SET check_count = 0 WHERE check_count IS NULL;"
        )
    conn.commit()


def upsert_dataframe(conn: sqlite3.Connection, df: pd.DataFrame) -> int:
    """Upsert rows by ads_id, preserving recheck-managed columns. Returns row count.

    On insert: first_seen = scrape_date, availability_status = 'active', check_count = 0.
    On conflict (existing listing re-scraped): scrape columns are refreshed and the
    listing is re-affirmed live (status -> 'active', gone_at cleared, last_checked_at
    bumped to this scrape_date) — but first_seen and check_count are left untouched.
    """
    if 'ads_id' not in df.columns:
        raise ValueError("DataFrame missing 'ads_id' column — cannot upsert.")

    df = df.drop_duplicates(subset='ads_id').copy()
    for col in SCRAPE_COLUMNS:
        if col not in df.columns:
            df[col] = None
    df = df[SCRAPE_COLUMNS]

    # NaN -> None so SQLite stores NULL.
    df = df.astype(object).where(pd.notnull(df), None)

    insert_cols = SCRAPE_COLUMNS + ['first_seen']
    placeholders = ', '.join('?' * len(insert_cols))
    update_set = ', '.join(
        f"{c} = excluded.{c}" for c in SCRAPE_COLUMNS if c != 'ads_id'
    )
    sql = (
        f"INSERT INTO {config.DB_TABLE} ({', '.join(insert_cols)}, "
        f"availability_status, check_count) "
        f"VALUES ({placeholders}, 'active', 0) "
        f"ON CONFLICT(ads_id) DO UPDATE SET "
        f"{update_set}, "
        f"availability_status = 'active', "
        f"gone_at = NULL, "
        f"last_checked_at = excluded.scrape_date"
    )

    scrape_date_idx = SCRAPE_COLUMNS.index('scrape_date')
    rows = df.values.tolist()
    params = [row + [row[scrape_date_idx]] for row in rows]  # first_seen = scrape_date
    conn.executemany(sql, params)
    return len(df)


def load_processed_files():
    processed_files = list(config.PROCESSED_DATA_DIR.glob('*.csv'))
    if not processed_files:
        logger.warning("No processed CSV files found.")
        return

    conn = sqlite3.connect(config.DB_FILE)
    conn.execute("PRAGMA journal_mode=WAL;")
    ensure_schema(conn)
    for idx_sql in CREATE_INDEXES_SQL:
        conn.execute(idx_sql)

    total_upserted = 0

    for csv_path in processed_files:
        try:
            df = pd.read_csv(csv_path)
            # ON CONFLICT(ads_id) upsert preserves recheck-managed columns; no DELETE needed.
            count = upsert_dataframe(conn, df)
            conn.commit()

            # Once loaded, the CSVs are regenerable from the DB — delete, don't archive.
            csv_path.unlink()

            # Raw file lives in a per-state subdir (data/raw/<state>/<name>.csv).
            # Search recursively so we find it regardless of nesting depth.
            raw_file = next(config.RAW_DATA_DIR.rglob(csv_path.name), None)
            if raw_file:
                raw_file.unlink()

            logger.info(f"Loaded {count} rows from {csv_path.name}; processed + raw CSVs removed.")
            total_upserted += count

        except Exception as e:
            conn.rollback()
            logger.error(f"Error loading {csv_path.name}: {e}")
            continue

    deleted = _dedup(conn)
    if deleted:
        logger.info(f"Dedup removed {deleted} content-duplicate rows (kept lowest ads_id per group).")

    conn.close()
    logger.info(f"Done. Total rows upserted: {total_upserted}. DB: {config.DB_FILE}")

    # Sweep combined _ALL_ files from raw subdirs — skipped by clean.py so they
    # never get a processed file and would otherwise accumulate indefinitely.
    for p in config.RAW_DATA_DIR.rglob('*.csv'):
        if config.SCRAPED_COMBINED_MARKER in p.name:
            p.unlink()
            logger.info(f"Swept combined file: {p.name}")


if __name__ == "__main__":
    load_processed_files()
