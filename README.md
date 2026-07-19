# MudahRentDataAnalysis

## Overview
Pulls rental property listings from Mudah.my via its public JSON search API, cleans the data, and stores it in a SQLite database.

Originally based on the HTML web-scraping approach by [Aditya Arie Wijaya](https://adtarie.net/posts/005-webscraping-machinelearning-rent-pricing/). The current implementation uses Mudah's structured search API instead — ~25× faster, no HTML parsing, no Cloudflare challenges.

---

## How the Data Is Acquired

Mudah.my's listing pages are Next.js apps that hydrate listing data client-side from a public JSON endpoint:

```
GET https://search.mudah.my/v1/search
    ?category=2000             # properties (parent category)
    &type=let                  # rental (vs. 'sell')
    &region=<id>               # 1..17, one per Malaysian state (see config.REGION_CODES)
    &from=<offset>             # pagination offset (200 per page; sent as limit)
    &fields=all                # broadest field set the search endpoint serves
    &property_type_id=<id>     # optional: filter by type (see config.RESIDENTIAL_PROPERTY_TYPE_IDS)
```

A single request returns up to 200 listings with structured attributes: `monthly_rent`, `property_type_name`, `property_type_id`, `category_name`, `rooms_name`, `bathroom_name`, `size`, `building_name`, `subarea_name`, `region_name`, `date`, `ad_expiry`, `adview_url`, … — no HTML parsing.

**Depth cap:** the API returns an empty `data` array at offset ≥ ~9,984, no matter how many `total-results` it reports. To get full coverage of a large region, filter by `property_type_id` — each type has its own depth window. `iter_listings`/`scrape` accept `property_type_id`, and `scrape_all_types()` loops every residential type.

`scripts/mudah_api.py` wraps this:
- `search(region, offset, property_type_id=None)` — one API call; retries 403/429/5xx with backoff + `Retry-After`
- `iter_listings(region, max_pages, property_type_id=None)` — paginates, stops early on a partial page
- `to_csv_row(item)` — maps an API item to the project's CSV schema
- `geocode_query(attributes)` — composes `building, subarea, region, Malaysia` for Nominatim

`scripts/scrape.py` orchestrates: pull listings → transform → geocode each via `geopy`/Nominatim (cached in `data/geocache.json`) → write CSV.

`config.REGION_CODES` was populated by a one-shot probe of each state's listing page `__NEXT_DATA__.initialQuery` (`scripts/discover_regions.py`, since deleted — see git history if the IDs ever need regenerating).

### Trade-offs vs. HTML scraping
- **Pro:** ~25× faster (1 page Selangor: 12s vs 5min). No Cloudflare 403s. Cleaner structured data.
- **Con:** No street-level address — only `building_name + subarea_name + region_name`. Geocoding precision is coarser for listings that previously had a street address. Acceptable for state/region-level analytics.
- **Risk:** API is undocumented. If Mudah changes the param names or response shape, the scraper breaks. Run the live smoke test before a scrape to catch drift early: `MUDAH_LIVE_TEST=1 pytest tests/test_api_live.py` (hits the real API; the normal suite skips it).

---

## Folder Structure

```
MudahRentDataAnalysis/
├── config.py                  # Paths, API constants, REGION_CODES
├── requirements.txt           # Pinned dependencies
├── run_pipeline.py            # Single-command pipeline runner
│
├── scripts/
│   ├── scrape.py              # API → CSV (data/raw/)
│   ├── clean.py               # Clean raw CSVs → data/processed/
│   ├── load_to_db.py          # Upsert processed CSVs → data/mudah_rent.db
│   ├── mudah_api.py           # Mudah search API client + transformer
│   ├── backfill_geocode.py    # Backfill missing lat/lon in DB
│   ├── recheck.py             # Optional: track listing availability (active/rented/expired)
│   └── logger.py              # Shared logging
│
├── tests/
│   ├── conftest.py            # Shared fixtures
│   ├── test_clean.py          # Clean function tests
│   ├── test_load.py           # DB upsert tests
│   └── test_mudah_api.py      # API client + transformer tests (mocked)
│
├── logs/
│   └── pipeline.log
│
└── data/
    ├── raw/                   # Scraped CSV (staging for clean step)
    ├── processed/             # Cleaned CSV (staging for DB load)
    ├── mapping.csv            # Property type standardization
    ├── geocache.json          # Geocoding cache (query → lat/lon)
    └── mudah_rent.db          # SQLite database (source of truth)
```

---

## Pipeline

```
scrape.py      →   data/raw/*.csv          (search API + geocode)
clean.py       →   data/processed/*.csv    (numeric rent/size, CPI mapping, category filter)
load_to_db.py  →   data/mudah_rent.db      (upsert on ads_id, batched)
```

**Non-residential listings are dropped at the clean step.** `clean.py` filters on the
API's `category_name` (stored as `category_id`), discarding `config.EXCLUDED_CATEGORIES`
= `Commercial Property` and `Land`. Room rentals are kept.

The filter keys on category, not `property_type`, because the type names don't
partition cleanly: `Shop lot` is commercial while `Shoplot` rooms are residential,
and ids `31`/`36` return `Residential`/`Mixed Development` but are vacant land.
`category_name` is a 5-value closed set — `Apartment / Condominium`, `House`,
`Room`, `Commercial Property`, `Land` — and survives Mudah adding new type ids.

> Drift canary: if the `Other` CPI bucket's average rent jumps (it should sit near
> RM2,900), a new non-residential category is leaking in. Re-probe the type ids.

After `load_to_db.py` runs, the loaded raw and processed CSVs are deleted — the DB is the source of truth.

All pipeline activity logged to `logs/pipeline.log`.

---

## Getting Started

### 1. Setup environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Run the pipeline

**Option A — Single command (recommended):**

```bash
# Full pipeline: scrape ALL states + ALL residential types, then clean + load
python run_pipeline.py

# One state only
python run_pipeline.py --state selangor

# Skip scraping — clean and load existing raw files only
python run_pipeline.py --skip-scrape
```

`--state` must be a slug from `config.REGION_CODES`, e.g. `selangor`, `kuala-lumpur`, `johor`, `penang`, `sabah`, `sarawak`, etc. The API requires a region; there is no Malaysia-wide fetch.

**Option B — Step by step:**

```bash
# Step 1 — Scrape listings via API (interactive state/type pickers)
python scripts/scrape.py

# Step 2 — Clean raw data
python scripts/clean.py

# Step 3 — Load into SQLite
python scripts/load_to_db.py
```

### 3. Run tests

```bash
pytest -q
```

API client tests use the `responses` library to mock HTTP calls — no network required.

### 4. Backfill missing lat/lon (optional)

When Nominatim can't resolve an address (or Mudah's `building_name` is empty), lat/lon may be NULL. The backfill fills these using region+state fallback:

```bash
python scripts/backfill_geocode.py
```

- Groups null rows by `(region, state)` — one geocode call fills many rows
- Coords are region-centroid level (good for heatmaps, not street-level)
- Reuses `data/geocache.json`
- Always backup the DB before running: `cp data/mudah_rent.db data/mudah_rent.db.bak`

### 5. Re-check availability (optional)

Turns the static snapshot into time-series: which listings are still live, and whether
a gone listing left **early (rented)** or just **expired**.

```bash
python scripts/recheck.py             # re-check all due listings
python scripts/recheck.py --limit 50  # cap for a test run
```

- Uses the search API's per-listing lookup (`GET ?list_id=<id>` → item if live, empty if gone) — one cheap call each, no Cloudflare
- **Decaying cadence** (`config.RECHECK_DECAY`): young listings checked daily, then every 3 days, then weekly
- On disappearance, classifies via `ad_expiry`: gone before expiry → `rented`, at/after → `expired` (missing expiry → `expired`)
- Maintains in-place columns: `first_seen`, `last_checked_at`, `availability_status`, `gone_at`
- The loader's `ON CONFLICT` upsert preserves these across re-scrapes; `ensure_schema()` migrates older DBs by adding any missing columns
- Optional, separate pass — NOT part of `run_pipeline.py`. Back up the DB first.

---

## Configuration (`config.py`)

| Setting | Default | Description |
|---|---|---|
| `API_BASE_URL` | `https://search.mudah.my/v1/search` | Mudah search API endpoint |
| `API_CATEGORY_PROPERTY` | `"2000"` | Parent category for properties |
| `API_TYPE_RENT` | `"let"` | Rental filter (`sell` for sale) |
| `API_PAGE_SIZE` | `200` | Results per API page (server cap; sent as `limit`) |
| `API_FIELDS` | `"all"` | Return every attribute |
| `API_REQUEST_TIMEOUT` | `15` s | Per-request timeout |
| `API_MIN_DELAY` / `API_MAX_DELAY` | `0.5` / `1.5` s | Polite delay between API pages |
| `REGION_CODES` | 16 states | State slug → Mudah region_id |
| `EXCLUDED_CATEGORIES` | `Commercial Property`, `Land` | Non-residential categories dropped by `clean.py` |
| `RAW_DATA_DIR` | `data/raw/` | Scraped output |
| `PROCESSED_DATA_DIR` | `data/processed/` | Cleaned output |
| `DB_FILE` | `data/mudah_rent.db` | SQLite path |
| `GEO_CACHE_FILE` | `data/geocache.json` | Geocode cache |
| `LOG_FILE` | `logs/pipeline.log` | Pipeline log |
| `GEOLOCATION_TIMEOUT` | `5` s | Nominatim timeout |

---

## Dependencies

See `requirements.txt`. Key packages:

- `requests` — HTTP client for the Mudah search API
- `pandas` — Data processing (pulls in `numpy`)
- `geopy` — Address geocoding via Nominatim, `RateLimiter` (1 req/sec). Cached to `data/geocache.json`
- `pytest` + `responses` — Test runner with HTTP mocking
- `tqdm` — Progress bars
