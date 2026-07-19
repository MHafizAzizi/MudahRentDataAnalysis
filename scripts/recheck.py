"""Track listing availability over time.

Re-checks previously-scraped listings against the search API's per-listing lookup
(`mudah_api.lookup`) on a decaying cadence, and records whether each is still live.
When a listing disappears it's classified using `ad_expiry`:
  - gone BEFORE ad_expiry  -> 'rented'  (left the market early — demand signal)
  - gone AT/AFTER ad_expiry -> 'expired' (ad window simply lapsed)

Maintains in-place columns on the `properties` table: first_seen, last_checked_at,
availability_status, gone_at.

Optional, standalone pass — NOT part of run_pipeline.py. Back up the DB first:
    cp data/mudah_rent.db data/mudah_rent.db.bak
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config
import logging
import scripts.logger  # noqa: F401  — configures root handlers
from scripts import mudah_api
from scripts import load_to_db

logger = logging.getLogger("recheck")

import time
import random
import argparse
import sqlite3
from datetime import datetime, date
from typing import Optional
from tqdm import tqdm

_DATE_FMT = "%Y-%m-%d"


def _parse_date(value: Optional[str]) -> Optional[date]:
    """Parse a YYYY-MM-DD scrape/check date string to a date, or None."""
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], _DATE_FMT).date()
    except ValueError:
        return None


def due_for_check(first_seen: Optional[str], last_checked_at: Optional[str],
                  today: date) -> bool:
    """Decide whether a listing is due for a re-check under the decay policy.

    Cadence widens with listing age (config.RECHECK_DECAY): young listings are
    checked often, old ones rarely. Never-checked listings are always due.
    """
    if not last_checked_at:
        return True

    seen = _parse_date(first_seen) or today
    age_days = (today - seen).days

    interval = config.RECHECK_DECAY[-1][1]
    for age_lt, days in config.RECHECK_DECAY:
        if age_lt is not None and age_days < age_lt:
            interval = days
            break

    last = _parse_date(last_checked_at)
    if last is None:
        return True
    return (today - last).days >= interval


def classify_gone(ad_expiry: Optional[str], today: date) -> str:
    """Classify a disappeared listing as 'rented' (gone early) or 'expired'.

    Missing/unparseable ad_expiry defaults to 'expired'.
    """
    if ad_expiry:
        try:
            expiry = datetime.strptime(str(ad_expiry), config.AD_EXPIRY_FORMAT).date()
            return "rented" if today < expiry else "expired"
        except ValueError:
            pass
    return "expired"


def recheck(limit: Optional[int] = None):
    conn = sqlite3.connect(config.DB_FILE)
    load_to_db.ensure_schema(conn)

    rows = conn.execute(
        f"""
        SELECT ads_id, first_seen, last_checked_at, ad_expiry
        FROM {config.DB_TABLE}
        WHERE availability_status IS NULL
           OR availability_status NOT IN ('rented', 'expired')
        """
    ).fetchall()

    today = date.today()
    due = [r for r in rows if due_for_check(r[1], r[2], today)]
    if limit:
        due = due[:limit]

    if not due:
        logger.info("No listings due for re-check.")
        conn.close()
        return

    logger.info(f"Re-checking {len(due)} of {len(rows)} active listings.")
    today_str = today.strftime(_DATE_FMT)
    alive = gone = failed = 0

    for ads_id, first_seen, last_checked_at, ad_expiry in tqdm(due, desc="Re-checking"):
        try:
            data = mudah_api.lookup(ads_id)
        except Exception as e:
            failed += 1
            logger.warning(f"Lookup failed for {ads_id}: {e}")
            time.sleep(random.uniform(config.API_MIN_DELAY, config.API_MAX_DELAY))
            continue

        if data:
            conn.execute(
                f"""UPDATE {config.DB_TABLE}
                    SET last_checked_at = ?
                    WHERE ads_id = ?""",
                (today_str, ads_id),
            )
            alive += 1
        else:
            status = classify_gone(ad_expiry, today)
            conn.execute(
                f"""UPDATE {config.DB_TABLE}
                    SET availability_status = ?, gone_at = ?, last_checked_at = ?
                    WHERE ads_id = ?""",
                (status, today_str, today_str, ads_id),
            )
            gone += 1

        conn.commit()
        time.sleep(random.uniform(config.API_MIN_DELAY, config.API_MAX_DELAY))

    conn.close()
    logger.info(f"Done. Still active: {alive}, gone: {gone}, failed: {failed}.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Re-check listing availability.")
    ap.add_argument("--limit", type=int, default=None, help="Max listings to check (for testing).")
    args = ap.parse_args()
    recheck(limit=args.limit)
