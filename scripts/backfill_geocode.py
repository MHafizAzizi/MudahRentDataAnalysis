"""Backfill missing lat/lon in DB.

Strategy:
- Query DB for rows where latitude IS NULL.
- Group by (region, state) — one geocode call fills all matching rows.
- Use same fallback chain as scraper.
- Update DB in batches.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from scripts.logger import get_logger
from scripts.scrape import geocode as _geocode, _load_geocache, _save_geocache

logger = get_logger("backfill_geocode")

import sqlite3
from tqdm import tqdm


def backfill():
    conn = sqlite3.connect(config.DB_FILE)
    cur = conn.cursor()

    cur.execute(f"""
        SELECT DISTINCT region, state
        FROM {config.DB_TABLE}
        WHERE latitude IS NULL OR longitude IS NULL
    """)
    pairs = cur.fetchall()
    logger.info(f"Found {len(pairs)} unique (region, state) pairs to geocode")

    cache = _load_geocache()
    updated = 0

    for region, state in tqdm(pairs, desc="Backfilling"):
        queries = []
        if region and state:
            queries.append(f"{region}, {state}, Malaysia")
        if state:
            queries.append(f"{state}, Malaysia")

        lat = lon = None
        for q in queries:
            lat, lon = _geocode(q, cache)
            if lat is not None:
                break

        if lat is None:
            logger.warning(f"Failed: region={region}, state={state}")
            continue

        cur.execute(f"""
            UPDATE {config.DB_TABLE}
            SET latitude = ?, longitude = ?
            WHERE (latitude IS NULL OR longitude IS NULL)
              AND region IS ? AND state IS ?
        """, (lat, lon, region, state))
        updated += cur.rowcount
        conn.commit()

    _save_geocache(cache)
    conn.close()
    logger.info(f"Updated {updated} rows")


if __name__ == "__main__":
    backfill()
