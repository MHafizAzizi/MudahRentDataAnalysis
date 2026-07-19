"""Mudah rental scraper — API-based.

Fetches property rental listings via Mudah's public search API,
geocodes the resulting addresses, and writes a CSV.
"""
import sys
import sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
import logging
import scripts.logger  # noqa: F401  — configures root handlers
from scripts import mudah_api

logger = logging.getLogger("webscrape")

import re
import json
import pandas as pd
from tqdm import tqdm
from typing import List, Tuple, Optional
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
        json.dump(cache, f, ensure_ascii=False)


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


def scrape(state: str, max_pages: int = 500,
           property_type_id: Optional[int] = None,
           skip_known: bool = True) -> pd.DataFrame:
    """Scrape rental listings for `state` (URL slug), paginating up to max_pages.

    Pass property_type_id to scrape a single property type (its own depth window).
    Pass skip_known=False to re-scrape listings already in the DB.
    """
    state_key = (state or "").strip().lower()
    if state_key not in config.REGION_CODES:
        raise ValueError(
            f"Unknown state {state_key!r}. Known: {sorted(config.REGION_CODES)}"
        )
    region = config.REGION_CODES[state_key]

    geocache = _load_geocache()
    rows = []
    today = datetime.now().strftime("%Y-%m-%d")

    logger.info(f"Fetching listings: state={state_key} region={region} max_pages={max_pages} property_type_id={property_type_id}")
    items = list(tqdm(
        mudah_api.iter_listings(
            region=region, max_pages=max_pages,
            property_type_id=property_type_id,
        ),
        desc="Fetching listings",
        total=max_pages * config.API_PAGE_SIZE,
        unit=" listing",
    ))
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


def _slug(text: str) -> str:
    """Filesystem-safe slug for a property-type name (e.g. '2.5-storey Terraced House')."""
    s = re.sub(r"[^\w]+", "_", text.strip().lower())
    return s.strip("_") or "type"


def scrape_all_types(state: str, max_pages: int = 500,
                     skip_known: bool = True,
                     property_type_ids: Optional[List[int]] = None) -> pd.DataFrame:
    """Scrape residential property types for `state`, one filtered query each.

    The API caps pagination at ~9,984 results per query (API_OFFSET_CAP), but each
    property type's total is well under that — so scraping per type yields full
    coverage where an unfiltered scrape would be truncated. Dedups by ads_id since
    a listing can occasionally surface under more than one type.

    Pass property_type_ids to scrape only a subset; None = every residential type.

    Results are saved under data/raw/<state>/:
      - one CSV per property type, written immediately after that type finishes
        (a crash-safe checkpoint — a mid-run failure keeps completed types), and
      - a combined deduped CSV (<state>_ALL_<ts>.csv) once all types are done.
    Returns the combined DataFrame (deduped by ads_id).
    """
    if property_type_ids is None:
        type_items = list(config.RESIDENTIAL_PROPERTY_TYPE_IDS.items())
    else:
        type_items = [(pid, config.RESIDENTIAL_PROPERTY_TYPE_IDS[pid])
                      for pid in property_type_ids]

    state_slug = (state or "malaysia").strip().lower()
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    out_dir = config.RAW_DATA_DIR / state_slug
    out_dir.mkdir(parents=True, exist_ok=True)

    frames = []
    for pt_id, name in type_items:
        logger.info(f"Scraping type {pt_id} ({name})")
        df = scrape(state, max_pages=max_pages,
                    property_type_id=pt_id, skip_known=skip_known)
        logger.info(f"  {name}: {len(df)} rows")
        if df.empty:
            continue
        frames.append(df)
        fname = config.SCRAPED_TYPE_FILENAME_TEMPLATE.format(
            state=state_slug, type_id=pt_id, type_slug=_slug(name),
            timestamp=timestamp,
        )
        type_path = out_dir / fname
        df.to_csv(type_path, index=False)
        logger.info(f"  Saved {len(df)} rows -> {type_path}")

    if not frames:
        logger.warning("No rows scraped for any selected type.")
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    if "ads_id" in combined.columns:
        before = len(combined)
        combined = combined.drop_duplicates(subset="ads_id").reset_index(drop=True)
        logger.info(f"Combined {before} rows -> {len(combined)} unique after dedup")

    combined_path = out_dir / config.SCRAPED_COMBINED_FILENAME_TEMPLATE.format(
        state=state_slug, timestamp=timestamp,
    )
    combined.to_csv(combined_path, index=False)
    logger.info(f"Saved combined {len(combined)} rows -> {combined_path}")

    return combined


def _prompt_state() -> Optional[str]:
    """Show a numbered list of known states; return the chosen URL slug.

    Press Enter alone to scrape ALL states. Returns None for all, else a slug.
    """
    states = sorted(config.REGION_CODES)
    col_w = max(len(s) for s in states) + 2
    per_row = 3
    print(f"\nAvailable states ({len(states)}):")
    for i, slug in enumerate(states, 1):
        label = f"{i:3}. {slug:<{col_w}}"
        print(f"  {label}", end="\n" if i % per_row == 0 or i == len(states) else "")

    print("\n  Press Enter      : scrape ALL states")

    while True:
        raw = input(f"\nSelect a state 1-{len(states)} (or type its slug): ").strip().lower()
        if not raw:
            print(f"  Scraping ALL {len(states)} states.")
            return None
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(states):
                return states[idx - 1]
        elif raw in config.REGION_CODES:
            return raw
        print(f"  ✗ invalid — enter 1-{len(states)}, a valid slug, or Enter for all.")


def _prompt_property_types() -> Optional[List[int]]:
    """Show a numbered list of residential property types; return selected ids.

    Accepts numbers (1,3,5), ranges (1-10), or combinations (1-5,8,12-15).
    Press Enter alone to scrape ALL types. Returns None for all, else id list.
    """
    types = list(config.RESIDENTIAL_PROPERTY_TYPE_IDS.items())  # [(id, name), ...]
    col_w = max(len(name) for _, name in types) + 2
    per_row = 2
    print(f"\nAvailable residential property types ({len(types)}):")
    for i, (_pid, name) in enumerate(types, 1):
        label = f"{i:3}. {name:<{col_w}}"
        print(f"  {label}", end="\n" if i % per_row == 0 or i == len(types) else "")

    print("\n\nSelect property types to scrape:")
    print("  Numbers / ranges : 1,3,5  |  1-10  |  1-5,8,12-15")
    print("  Press Enter      : scrape ALL types")

    raw = input("\nSelection: ").strip().lower()
    if not raw:
        return None

    selected: List[int] = []
    seen: set = set()

    def _add(idx: int) -> None:
        pid = types[idx - 1][0]
        if pid not in seen:
            seen.add(pid)
            selected.append(pid)

    for token in (t.strip() for t in raw.split(",") if t.strip()):
        range_m = re.match(r'^(\d+)-(\d+)$', token)
        if range_m:
            lo, hi = int(range_m.group(1)), int(range_m.group(2))
            for idx in range(lo, hi + 1):
                if 1 <= idx <= len(types):
                    _add(idx)
                else:
                    print(f"  ✗ {idx} out of range (1–{len(types)})")
        elif token.isdigit():
            idx = int(token)
            if 1 <= idx <= len(types):
                _add(idx)
            else:
                print(f"  ✗ {idx} out of range (1–{len(types)})")
        else:
            print(f"  ✗ '{token}' not a number/range — skipped")

    if not selected:
        print("  No valid selection — scraping ALL types.")
        return None

    names = ", ".join(config.RESIDENTIAL_PROPERTY_TYPE_IDS[p] for p in selected)
    print(f"\n  Selected {len(selected)} type(s): {names}")
    return selected


def main():
    print("\n=== Mudah Rent Scraper ===")
    state_choice = _prompt_state()  # None = all, slug = one
    pt_ids = _prompt_property_types()

    all_states = sorted(config.REGION_CODES) if state_choice is None else [state_choice]
    total_rows = 0

    for i, state in enumerate(all_states, 1):
        if len(all_states) > 1:
            print(f"\n[{i}/{len(all_states)}] Scraping state: {state}")
        # scrape_all_types writes per-type checkpoints + a combined CSV under
        # data/raw/<state>/ as it goes, so no extra write is needed here.
        df = scrape_all_types(state, property_type_ids=pt_ids)
        out_dir = config.RAW_DATA_DIR / state.strip().lower()
        total_rows += len(df)
        print(f"  {state}: {len(df)} unique rows → {out_dir}")

    if len(all_states) > 1:
        print(f"\nDone. {total_rows} total unique rows across {len(all_states)} states.")
    else:
        print(f"\nDone. {total_rows} unique rows.")


if __name__ == "__main__":
    main()
