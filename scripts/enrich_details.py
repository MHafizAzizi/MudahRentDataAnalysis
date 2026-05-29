"""Backfill detail-only fields the search API never returns.

The Mudah search API omits `furnished`, `facilities`, `additional_facilities`
and `body`. These exist only on the per-listing detail page, hydrated from a
`__NEXT_DATA__` JSON blob. This script:

- Selects DB rows missing those fields that still have an `adviewUrl`.
- Fetches each detail page (cloudscraper, since detail pages sit behind Cloudflare).
- Parses `props.initialState.adDetails.byID.<list_id>.attributes`.
- UPDATEs the row.

Optional, separate pass — NOT part of the main pipeline. Slow (one HTTP request
per listing) and Cloudflare-prone, which is exactly why the project moved to the
API for bulk acquisition. Always back up the DB first:
    cp data/mudah_rent.db data/mudah_rent.db.bak
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from scripts.logger import get_logger

logger = get_logger("enrich_details")

import json
import re
import time
import random
import argparse
import sqlite3
import cloudscraper
from tqdm import tqdm

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.S,
)


def parse_detail(html: str, list_id: str) -> dict:
    """Extract enrichment fields from a detail page's __NEXT_DATA__ blob.

    Returns a dict with keys from config.ENRICH_FIELDS; missing values are ''.
    Raises ValueError if the blob or the ad's attributes can't be located.
    """
    m = _NEXT_DATA_RE.search(html)
    if not m:
        raise ValueError("no __NEXT_DATA__ script found")

    data = json.loads(m.group(1))
    by_id = (
        data.get("props", {})
        .get("initialState", {})
        .get("adDetails", {})
        .get("byID", {})
    )
    if not by_id:
        raise ValueError("no adDetails.byID in __NEXT_DATA__")

    ad = by_id.get(str(list_id)) or next(iter(by_id.values()))
    attrs = ad.get("attributes", {})

    # furnished / facilities / additional_facilities are entries in categoryParams,
    # an array of {"id": ..., "value": ...}. body is a top-level attribute.
    params = {p.get("id"): p.get("value") for p in attrs.get("categoryParams", [])}

    out = {}
    for field in config.ENRICH_FIELDS:
        if field == "body":
            out[field] = attrs.get("body") or ""
        else:
            out[field] = params.get(field) or ""
    return out


def _list_id_from_url(url: str) -> str:
    """Mudah adview URLs end with -<list_id>.htm."""
    m = re.search(r"-(\d+)\.htm", url or "")
    return m.group(1) if m else ""


def _rows_needing_enrichment(conn: sqlite3.Connection):
    """ads_id + adviewUrl for rows missing any enrichment field but with a URL."""
    missing = " OR ".join(
        f"({f} IS NULL OR {f} = '')" for f in config.ENRICH_FIELDS
    )
    cur = conn.execute(
        f"""
        SELECT ads_id, adviewUrl
        FROM {config.DB_TABLE}
        WHERE adviewUrl IS NOT NULL AND adviewUrl != ''
          AND ({missing})
        """
    )
    return cur.fetchall()


def enrich(limit: int = None):
    conn = sqlite3.connect(config.DB_FILE)
    rows = _rows_needing_enrichment(conn)
    if limit:
        rows = rows[:limit]

    if not rows:
        logger.info("No rows need enrichment.")
        conn.close()
        return

    logger.info(f"Enriching {len(rows)} listings from detail pages.")
    scraper = cloudscraper.create_scraper(
        browser={"browser": "firefox", "platform": "windows", "mobile": False},
        delay=10,
    )

    updated = 0
    failed = 0
    set_clause = ", ".join(f"{f} = ?" for f in config.ENRICH_FIELDS)

    for ads_id, url in tqdm(rows, desc="Enriching"):
        list_id = _list_id_from_url(url) or str(ads_id)
        try:
            resp = scraper.get(url, timeout=config.ENRICH_REQUEST_TIMEOUT)
            resp.raise_for_status()
            fields = parse_detail(resp.text, list_id)
        except Exception as e:
            failed += 1
            logger.warning(f"Failed {ads_id} ({url}): {e}")
            time.sleep(random.uniform(config.ENRICH_MIN_DELAY, config.ENRICH_MAX_DELAY))
            continue

        values = [fields[f] for f in config.ENRICH_FIELDS] + [ads_id]
        conn.execute(
            f"UPDATE {config.DB_TABLE} SET {set_clause} WHERE ads_id = ?",
            values,
        )
        conn.commit()
        updated += 1
        time.sleep(random.uniform(config.ENRICH_MIN_DELAY, config.ENRICH_MAX_DELAY))

    conn.close()
    logger.info(f"Done. Enriched {updated}, failed {failed}.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Backfill detail-only listing fields.")
    ap.add_argument("--limit", type=int, default=None, help="Max listings to enrich (for testing).")
    args = ap.parse_args()
    enrich(limit=args.limit)
