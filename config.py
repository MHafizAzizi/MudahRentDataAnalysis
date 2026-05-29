"""
Configuration for Mudah Rent Data Analysis project.
"""

from pathlib import Path

# --- Project Paths ---
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
ARCHIVED_DATA_DIR = DATA_DIR / "archived"
OLD_RAW_DIR = DATA_DIR / "old" / "raw"
MAPPING_FILE = PROJECT_ROOT / "data" / "mapping.csv"  # Adjust if mapping file location differs

# SQLite database
DB_FILE = DATA_DIR / "mudah_rent.db"
DB_TABLE = "properties"

# Ensure directories exist
RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
ARCHIVED_DATA_DIR.mkdir(parents=True, exist_ok=True)
OLD_RAW_DIR.mkdir(parents=True, exist_ok=True)

# --- Web Scraping Configuration ---
BASE_URL = "https://www.mudah.my"

# Cloudscraper setup
SCRAPER_CONFIG = {
    "browser": "firefox",
    "platform": "windows",
    "mobile": False,
    "delay": 10  # General delay for scraper session
}

# Request delays (in seconds)
MIN_DELAY = 3
MAX_DELAY = 7
BASE_SLEEP_TIME = 2  # Sleep time between requests during scraping

# Property attributes to extract
PROPERTY_ATTRIBUTES = {
    "body",
    "address",
    "category_id",
    "monthly_rent",
    "property_type",
    "state",
    "region",
    "rooms",
    "bathroom",
    "size",
    "furnished",
    "facilities",
    "additional_facilities",
    "latitude",
    "longitude",
    "publishedDatetime",
    "scrape_date",
    "ads_id",
    "adviewUrl",
}

# Property categories to exclude from scraping
EXCLUDED_CATEGORIES = {
    "Commercial Property, For rent",
    "Land, For rent"
}

# --- Geolocation Configuration ---
GEOLOCATOR_USER_AGENT = "mudah_rent_analysis/1.0"
GEOLOCATION_TIMEOUT = 5  # seconds
GEO_CACHE_FILE = DATA_DIR / "geocache.json"

# --- Logging Configuration ---
LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "pipeline.log"
LOG_DIR.mkdir(exist_ok=True)

# --- Data Cleaning Configuration ---
# Output filename format for scraped data
SCRAPED_DATA_FILENAME_TEMPLATE = "Scraped_Data_Page{start}to{end}({timestamp})({state}).csv"

# Per-state / per-type output layout (data/raw/<state>/).
# Per-type files are written incrementally as each type finishes (crash-safe
# checkpoints). The combined file (_ALL_) is a deduped convenience snapshot.
# 2_clean.py processes the per-type files and SKIPS _ALL_ files to avoid
# double-counting (3_load_to_db upserts by ads_id, collapsing any overlap).
SCRAPED_TYPE_FILENAME_TEMPLATE = "{state}_{type_id}_{type_slug}_{timestamp}.csv"
SCRAPED_COMBINED_FILENAME_TEMPLATE = "{state}_ALL_{timestamp}.csv"
SCRAPED_COMBINED_MARKER = "_ALL_"

# Datetime format for parsing
DATETIME_FORMAT = "%m/%d/%Y"

# --- API Configuration ---
API_BASE_URL = "https://search.mudah.my/v1/search"
API_CATEGORY_PROPERTY = "2000"
API_TYPE_RENT = "let"
API_PAGE_SIZE = 200  # Server caps a page at 200 (live-probed); >200 silently truncates.
                     # Was 24 — the API ignored it and returned 200 anyway, so paging by
                     # 24 re-fetched the same rows ~8x. Sending limit + paging by 200 fixes it.
API_FIELDS = "all"
API_REQUEST_TIMEOUT = 15
API_MIN_DELAY = 0.5  # seconds between API calls (polite)
API_MAX_DELAY = 1.5

# Desktop UA — Mudah serves a stripped variant to mobile UAs
API_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Retry policy — Mudah returns 429 (with Retry-After) and 403 (rate limit) under load
API_MAX_RETRIES = 4
API_BACKOFF_BASE = 2.0      # seconds; exponential: base * 2**attempt
API_RETRY_MAX_WAIT = 300    # cap any single backoff/Retry-After at 5 min

# Empirical depth cap: the API returns an empty data array at offset >= ~9984,
# regardless of total-results. Filter per property_type_id to get a fresh window.
API_OFFSET_CAP = 9984

# Residential property_type_id -> name (discovered via API probe 2026-05-29).
# Commercial types (21=Office space, 22=Shop lot, 23=Warehouse/Factory, 24=Others)
# are excluded — this is a residential rental project. Each type's total is well
# under API_OFFSET_CAP, so scraping per type bypasses the depth cap.
RESIDENTIAL_PROPERTY_TYPE_IDS = {
    1: "Condominium",
    2: "Apartment",
    3: "Others",
    4: "Flat",
    5: "Service Residence",
    6: "Studio",
    7: "Duplex",
    8: "Townhouse Condo",
    11: "Bungalow House",
    12: "1-storey Terraced House",
    13: "2-storey Terraced House",
    14: "2.5-storey Terraced House",
    15: "3-storey Terraced House",
    16: "Semi-Detached House",
    17: "Others",
    18: "Townhouse",
    19: "1.5-storey Terraced House",
}

# --- Availability Re-check (recheck.py) ---
# The search API supports a per-listing lookup: GET ?list_id=<id>&fields=all returns
# the item in `data` if live, or an empty `data` array if gone (rented/expired).
# recheck.py uses this to track availability with a decaying check cadence.
RECHECK_DECAY = [(7, 1), (21, 3), (None, 7)]   # (age_days_lt, interval_days); None = catch-all
RECHECK_TERMINAL_STATUSES = {"rented", "expired"}
AD_EXPIRY_FORMAT = "%Y-%m-%d %H:%M:%S"

# --- Detail-page Enrichment ---
# The search API never returns furnished / facilities / additional_facilities / body
# (verified by live probe). They live only on the listing detail page, hydrated from
# __NEXT_DATA__ JSON. enrich_details.py fetches the HTML (via cloudscraper, behind
# Cloudflare) and backfills these columns. Run as an optional, separate pass.
ENRICH_FIELDS = ("furnished", "facilities", "additional_facilities", "body")
ENRICH_MIN_DELAY = 2.0   # seconds between detail-page fetches (polite; Cloudflare)
ENRICH_MAX_DELAY = 5.0
ENRICH_REQUEST_TIMEOUT = 30

# Region codes (state URL slug -> Mudah region_id) generated by scripts/discover_regions.py
REGION_CODES = {
    "johor": "12",
    "kedah": "2",
    "kelantan": "4",
    "kuala-lumpur": "9",
    "labuan": "17",
    "melaka": "11",
    "negeri-sembilan": "10",
    "pahang": "7",
    "penang": "3",
    "perak": "6",
    "perlis": "1",
    "putrajaya": "16",
    "sabah": "14",
    "sarawak": "13",
    "selangor": "8",
    "terengganu": "5",
}
