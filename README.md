# MudahRentDataAnalysis

## Overview
Scrapes rental property listings from Mudah.my, cleans the data, stores it in a SQLite database, and visualizes it via a Streamlit dashboard.

Based on the web scraping approach by [Aditya Arie Wijaya](https://adtarie.net/posts/005-webscraping-machinelearning-rent-pricing/).

---

## Folder Structure

```
MudahRentDataAnalysis/
├── config.py               # All paths, parameters, and settings
├── requirements.txt
│
├── scripts/
│   ├── 1_webscrape.py      # Scrape listings from Mudah.my → data/raw/
│   ├── 2_clean.py          # Clean raw CSVs → data/processed/
│   └── 3_load_to_db.py     # Upsert processed CSVs into SQLite → data/mudah_rent.db
│
├── app/
│   └── Streamlit.py        # Dashboard (reads from SQLite)
│
└── data/
    ├── raw/                # Scraped CSV/JSON files (source of truth)
    ├── processed/          # Cleaned CSVs (staging for DB load)
    ├── archived/           # Processed CSVs after DB load
    ├── old/raw/            # Raw CSVs after DB load
    ├── mapping.csv         # Property type standardization mapping
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

### 2. Configure paths

All settings are in `config.py`. Paths are relative to the project root — no manual edits needed for standard setup.

If your `mapping.csv` is in a different location, update `MAPPING_FILE` in `config.py`.

### 3. Run the pipeline

```bash
# Step 1 — Scrape listings
python scripts/1_webscrape.py
# Prompts: state, start page, end page, sleep time, output format (csv/json)

# Step 2 — Clean raw data
python scripts/2_clean.py

# Step 3 — Load into SQLite
python scripts/3_load_to_db.py

# Step 4 — Launch dashboard
streamlit run app/Streamlit.py
```

---

## Configuration (`config.py`)

| Setting | Default | Description |
|---|---|---|
| `RAW_DATA_DIR` | `data/raw/` | Scraped output location |
| `PROCESSED_DATA_DIR` | `data/processed/` | Cleaned output location |
| `DB_FILE` | `data/mudah_rent.db` | SQLite database path |
| `MIN_DELAY` / `MAX_DELAY` | `3` / `7` s | Random delay between page requests |
| `BASE_SLEEP_TIME` | `2` s | Base delay between property requests |
| `EXCLUDED_CATEGORIES` | Commercial, Land, Room | Property types skipped during scrape |

---

## Dependencies

See `requirements.txt`. Key packages:

- `cloudscraper` — Cloudflare bypass for scraping
- `beautifulsoup4` — HTML parsing
- `pandas` / `numpy` — Data processing
- `geopy` — Address geocoding
- `streamlit` — Dashboard
- `plotly` — Charts
