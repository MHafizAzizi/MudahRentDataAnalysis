"""Mudah rental scraper — API-based.

Fetches property rental listings via Mudah's public search API,
geocodes the resulting addresses, and writes a CSV.
"""
import sys
import sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from scripts.logger import get_logger
from scripts import mudah_api

logger = get_logger("webscrape")

import json
import pandas as pd
from tqdm import tqdm
from typing import Tuple, Optional
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from datetime import datetime

_GEOLOCATOR = Nominatim(
    user_agent=config.GEOLOCATOR_USER_AGENT,
    timeout=config.GEOLOCATION_TIMEOUT,
)
_GEOCODE = RateLimiter(
    _GEOLOCATOR.geocode,
    min_delay_seconds=1,
    max_retries=3,
    error_wait_seconds=5,
    swallow_exceptions=True,
)


def _load_geocache() -> dict:
    if config.GEO_CACHE_FILE.exists():
        with open(config.GEO_CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_geocache(cache: dict) -> None:
    with open(config.GEO_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def _load_known_ads_ids() -> set:
    """Return set of ads_id strings already in DB. Empty set if DB missing or inaccessible."""
    if not config.DB_FILE.exists():
        return set()
    try:
        with sqlite3.connect(config.DB_FILE) as conn:
            rows = conn.execute(f"SELECT ads_id FROM {config.DB_TABLE}").fetchall()
        return {r[0] for r in rows}
    except Exception as e:
        logger.warning(f"Could not load known ads_ids from DB: {e}")
        return set()


def geocode(query: str, cache: dict) -> Tuple[Optional[float], Optional[float]]:
    """Geocode `query` with cache. Returns (None, None) on miss/fail."""
    if not query:
        return (None, None)
    if query in cache:
        return tuple(cache[query])
    try:
        location = _GEOCODE(query)
    except (GeocoderTimedOut, GeocoderServiceError) as e:
        logger.warning(f"Geocode error for {query!r}: {e}")
        return (None, None)
    if not location:
        cache[query] = [None, None]
        return (None, None)
    result = (location.latitude, location.longitude)
    cache[query] = list(result)
    return result


def scrape(state: str, start_page: int, end_page: int, skip_known: bool = True) -> pd.DataFrame:
    """Scrape rental listings for `state` (URL slug) over the given page range."""
    state_key = (state or "").strip().lower()
    if state_key not in config.REGION_CODES:
        raise ValueError(
            f"Unknown state {state_key!r}. Known: {sorted(config.REGION_CODES)}"
        )
    region = config.REGION_CODES[state_key]
    max_pages = max(1, end_page - start_page + 1)

    geocache = _load_geocache()
    rows = []
    today = datetime.now().strftime("%Y-%m-%d")

    logger.info(f"Fetching listings: state={state_key} region={region} pages {start_page}..{end_page}")
    items = list(mudah_api.iter_listings(region=region, start_page=start_page, max_pages=max_pages))
    logger.info(f"API returned {len(items)} listings")

    if skip_known:
        known = _load_known_ads_ids()
        if known:
            before = len(items)
            items = [i for i in items if str(i.get("attributes", {}).get("list_id", "")) not in known]
            logger.info(f"Skipping {before - len(items)} known listings. {len(items)} to scrape.")

    for item in tqdm(items, desc="Transform + geocode"):
        row = mudah_api.to_csv_row(item)
        row["scrape_date"] = today
        query = mudah_api.geocode_query(item.get("attributes", {}))
        lat, lon = geocode(query, geocache)
        row["latitude"] = lat
        row["longitude"] = lon
        rows.append(row)

    _save_geocache(geocache)
    logger.info(f"Saved geocache with {len(geocache)} entries")
    return pd.DataFrame(rows)


def main():
    state = input("Enter the state (URL slug, e.g. 'selangor'): ").strip()
    start_page = int(input("Enter the starting page number: "))
    end_page = int(input("Enter the ending page number: "))

    df = scrape(state, start_page, end_page)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = config.SCRAPED_DATA_FILENAME_TEMPLATE.format(
        start=start_page, end=end_page, timestamp=timestamp, state=state or "malaysia"
    )
    out_path = config.RAW_DATA_DIR / filename
    df.to_csv(out_path, index=False)
    logger.info(f"Saved {len(df)} rows to {out_path}")


if __name__ == "__main__":
    main()
