# MudahRentDataAnalysis

## Overview
Scrapes rental property listings from Mudah.my, cleans the data, stores it in a SQLite database, and visualizes it via a Streamlit dashboard.

Based on the web scraping approach by [Aditya Arie Wijaya](https://adtarie.net/posts/005-webscraping-machinelearning-rent-pricing/).

---

## Folder Structure

```
MudahRentDataAnalysis/
├── config.py               # All paths, parameters, and settings
├── requirements.txt        # Pinned dependencies
├── run_pipeline.py         # Single-command pipeline runner
│
├── scripts/
│   ├── 1_webscrape.py      # Scrape listings from Mudah.my → data/raw/
│   ├── 2_clean.py          # Clean raw CSVs → data/processed/
│   ├── 3_load_to_db.py     # Upsert processed CSVs into SQLite → data/mudah_rent.db
│   └── logger.py           # Shared logging utility (console + file)
│
├── app/
│   └── Streamlit.py        # Dashboard (reads from SQLite)
│
├── tests/
│   ├── conftest.py         # Shared fixtures
│   ├── test_clean.py       # Unit tests for cleaning functions
│   └── test_load.py        # Unit tests for DB upsert
│
├── logs/
│   └── pipeline.log        # Pipeline run logs (auto-created)
│
└── data/
    ├── raw/                # Scraped CSV/JSON files (source of truth)
    ├── processed/          # Cleaned CSVs (staging for DB load)
    ├── archived/           # Processed CSVs after DB load
    ├── old/raw/            # Raw CSVs after DB load
    ├── mapping.csv         # Property type standardization mapping
    ├── geocache.json       # Geocoding cache (address → lat/lon)
    └── mudah_rent.db       # SQLite database
```

---

## Pipeline

```
1_webscrape.py   →   data/raw/*.csv
2_clean.py       →   data/processed/*.csv
3_load_to_db.py  →   data/mudah_rent.db  (upsert on ads_id)
Streamlit.py     →   reads from SQLite
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

# Skip scraping — clean and load existing raw files only
python run_pipeline.py --skip-scrape

# Malaysia-wide scrape with custom sleep time
python run_pipeline.py --start 1 --end 50 --sleep 3
```

**Option B — Step by step:**

```bash
# Step 1 — Scrape listings
python scripts/1_webscrape.py
# Prompts: state, start page, end page, sleep time, output format (csv/json)

# Step 2 — Clean raw data
python scripts/2_clean.py

# Step 3 — Load into SQLite
python scripts/3_load_to_db.py
```

### 3. Launch dashboard

```bash
streamlit run app/Streamlit.py
```

Dashboard includes:
- Key metrics (total listings, average rent, average size)
- Average rent by property type and state
- Furnishing status distribution
- Interactive property map (lat/lon, color-coded by type)
- Full property data table

### 4. Run tests

```bash
pytest tests/
```

---

## Configuration (`config.py`)

| Setting | Default | Description |
|---|---|---|
| `RAW_DATA_DIR` | `data/raw/` | Scraped output location |
| `PROCESSED_DATA_DIR` | `data/processed/` | Cleaned output location |
| `DB_FILE` | `data/mudah_rent.db` | SQLite database path |
| `GEO_CACHE_FILE` | `data/geocache.json` | Geocoding cache file |
| `LOG_FILE` | `logs/pipeline.log` | Pipeline log output |
| `MIN_DELAY` / `MAX_DELAY` | `3` / `7` s | Random delay between page requests |
| `BASE_SLEEP_TIME` | `2` s | Base delay between property requests |
| `GEOLOCATION_TIMEOUT` | `5` s | Nominatim geocoder timeout |
| `EXCLUDED_CATEGORIES` | Commercial, Land, Room | Property types skipped during scrape |

---

## Dependencies

See `requirements.txt` for pinned versions. Key packages:

- `cloudscraper` — Cloudflare bypass for scraping
- `beautifulsoup4` — HTML parsing
- `pandas` / `numpy` — Data processing
- `geopy` — Address geocoding (cached to `data/geocache.json`)
- `streamlit` — Dashboard
- `plotly` — Charts and interactive map
- `pytest` — Test runner
