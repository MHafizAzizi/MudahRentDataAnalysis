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
    &from=<offset>             # pagination offset (24 per page)
    &fields=all                # broadest field set the search endpoint serves
    &property_type_id=<id>     # optional: filter by type (see config.RESIDENTIAL_PROPERTY_TYPE_IDS)
```

A single request returns up to 24 listings with structured attributes: `monthly_rent`, `property_type_name`, `property_type_id`, `category_name`, `rooms_name`, `bathroom_name`, `size`, `building_name`, `subarea_name`, `region_name`, `date`, `ad_expiry`, `adview_url`, … — no HTML parsing.

> **Search endpoint does NOT return** `furnished`, `facilities`, `additional_facilities`, or `body`. These exist only on the per-listing detail page; the scraper emits empty values for them. Recover them with the optional `scripts/enrich_details.py` backfill (fetches each detail page's `__NEXT_DATA__` blob — see below).

**Depth cap:** the API returns an empty `data` array at offset ≥ ~9,984, no matter how many `total-results` it reports. To get full coverage of a large region, filter by `property_type_id` — each type has its own depth window. `iter_listings`/`scrape` accept `property_type_id`, and `scrape_all_types()` loops every residential type.

`scripts/mudah_api.py` wraps this:
- `search(region, offset, property_type_id=None)` — one API call; retries 403/429/5xx with backoff + `Retry-After`
- `iter_listings(region, start_page, max_pages, property_type_id=None)` — paginates, stops early on a partial page
- `to_csv_row(item)` — maps an API item to the project's CSV schema
- `geocode_query(attributes)` — composes `building, subarea, region, Malaysia` for Nominatim

`scripts/1_webscrape.py` orchestrates: pull listings → transform → geocode each via `geopy`/Nominatim (cached in `data/geocache.json`) → write CSV.

`scripts/discover_regions.py` is a one-shot script that enumerates region codes by inspecting each state's listing page `__NEXT_DATA__.initialQuery`. It populates `config.REGION_CODES`.

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
│   ├── 1_webscrape.py         # API → CSV (data/raw/)
│   ├── 2_clean.py             # Clean raw CSVs → data/processed/
│   ├── 3_load_to_db.py        # Upsert processed CSVs → data/mudah_rent.db
│   ├── mudah_api.py           # Mudah search API client + transformer
│   ├── discover_regions.py    # One-shot probe to enumerate REGION_CODES
│   ├── backfill_geocode.py    # Backfill missing lat/lon in DB
│   ├── enrich_details.py      # Optional: backfill furnished/facilities/body from detail pages
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
    ├── raw/                   # Scraped CSV (source of truth)
    ├── processed/             # Cleaned CSV (staging for DB load)
    ├── archived/              # Processed CSV after DB load
    ├── old/raw/               # Raw CSV after DB load
    ├── mapping.csv            # Property type standardization
    ├── geocache.json          # Geocoding cache (query → lat/lon)
    └── mudah_rent.db          # SQLite database
```

---

## Pipeline

```
1_webscrape.py   →   data/raw/*.csv          (search API + geocode)
2_clean.py       →   data/processed/*.csv    (numeric rent/size, CPI mapping)
3_load_to_db.py  →   data/mudah_rent.db      (upsert on ads_id, batched)
```

After `3_load_to_db.py` runs:
- `data/processed/file.csv` → `data/archived/`
- `data/raw/file.csv` → `data/old/raw/`

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
# Full pipeline: scrape + clean + load
python run_pipeline.py --state selangor --start 1 --end 10

# Full coverage: scrape every residential property type (bypasses the ~10k depth cap)
python run_pipeline.py --state selangor --all-types

# Skip scraping — clean and load existing raw files only
python run_pipeline.py --skip-scrape
```

`--state` must be a slug from `config.REGION_CODES`, e.g. `selangor`, `kuala-lumpur`, `johor`, `penang`, `sabah`, `sarawak`, etc. The API requires a region; there is no Malaysia-wide fetch.

**Option B — Step by step:**

```bash
# Step 1 — Scrape listings via API
python scripts/1_webscrape.py
# Prompts: state slug, start page, end page

# Step 2 — Clean raw data
python scripts/2_clean.py

# Step 3 — Load into SQLite
python scripts/3_load_to_db.py
```

### 3. Run tests

```bash
pytest -q
```

API client tests use the `responses` library to mock HTTP calls — no network required.

### 4. Refresh region codes (rare)

If Mudah ever rotates region IDs, regenerate them:

```bash
python scripts/discover_regions.py
```

Then paste the printed `REGION_CODES = { ... }` block into `config.py`.

### 5. Backfill missing lat/lon (optional)

When Nominatim can't resolve an address (or Mudah's `building_name` is empty), lat/lon may be NULL. The backfill fills these using region+state fallback:

```bash
python scripts/backfill_geocode.py
```

- Groups null rows by `(region, state)` — one geocode call fills many rows
- Coords are region-centroid level (good for heatmaps, not street-level)
- Reuses `data/geocache.json`
- Always backup the DB before running: `cp data/mudah_rent.db data/mudah_rent.db.bak`

### 6. Enrich detail-only fields (optional)

`furnished`, `facilities`, `additional_facilities`, and `body` are NOT in the search
API response — only on each listing's detail page. This backfill fetches those pages
and fills the columns:

```bash
python scripts/enrich_details.py            # all rows missing those fields
python scripts/enrich_details.py --limit 50 # cap for a test run
```

- Selects DB rows that have an `adviewUrl` but are missing any enrichment field
- Parses the detail page's `__NEXT_DATA__` JSON (`furnished`/`facilities`/`additional_facilities` from `categoryParams`, `body` from attributes)
- Uses `cloudscraper` (detail pages sit behind Cloudflare) with polite delays — slow, one request per listing
- Optional, separate pass — NOT part of `run_pipeline.py`
- Always back up the DB first: `cp data/mudah_rent.db data/mudah_rent.db.bak`

---

## Configuration (`config.py`)

| Setting | Default | Description |
|---|---|---|
| `API_BASE_URL` | `https://search.mudah.my/v1/search` | Mudah search API endpoint |
| `API_CATEGORY_PROPERTY` | `"2000"` | Parent category for properties |
| `API_TYPE_RENT` | `"let"` | Rental filter (`sell` for sale) |
| `API_PAGE_SIZE` | `24` | Results per API page |
| `API_FIELDS` | `"all"` | Return every attribute |
| `API_REQUEST_TIMEOUT` | `15` s | Per-request timeout |
| `API_MIN_DELAY` / `API_MAX_DELAY` | `0.5` / `1.5` s | Polite delay between API pages |
| `REGION_CODES` | 16 states | State slug → Mudah region_id |
| `RAW_DATA_DIR` | `data/raw/` | Scraped output |
| `PROCESSED_DATA_DIR` | `data/processed/` | Cleaned output |
| `DB_FILE` | `data/mudah_rent.db` | SQLite path |
| `GEO_CACHE_FILE` | `data/geocache.json` | Geocode cache |
| `LOG_FILE` | `logs/pipeline.log` | Pipeline log |
| `GEOLOCATION_TIMEOUT` | `5` s | Nominatim timeout |
| `EXCLUDED_CATEGORIES` | Commercial, Land | Categories ignored at clean step |

---

## Dependencies

See `requirements.txt`. Key packages:

- `requests` — HTTP client for the Mudah search API
- `cloudscraper` — Used only by `discover_regions.py` (HTML inspection of listing pages, which sit behind Cloudflare)
- `beautifulsoup4` — Region-discovery HTML parsing
- `pandas` / `numpy` — Data processing
- `geopy` — Address geocoding via Nominatim, `RateLimiter` (1 req/sec). Cached to `data/geocache.json`
- `pytest` + `responses` — Test runner with HTTP mocking
- `tqdm` — Progress bars
