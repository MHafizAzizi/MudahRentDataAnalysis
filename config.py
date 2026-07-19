"""
Configuration for Mudah Rent Data Analysis project.
"""

from pathlib import Path

# --- Project Paths ---
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
MAPPING_FILE = DATA_DIR / "mapping.csv"

# SQLite database
DB_FILE = DATA_DIR / "mudah_rent.db"
DB_TABLE = "properties"

# Ensure directories exist
RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)

# --- Geolocation Configuration ---
GEOLOCATOR_USER_AGENT = "mudah_rent_analysis/1.0"
GEOLOCATION_TIMEOUT = 5  # seconds
GEO_CACHE_FILE = DATA_DIR / "geocache.json"

# --- Logging Configuration ---
LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "pipeline.log"
LOG_DIR.mkdir(exist_ok=True)

# --- Data Cleaning Configuration ---
# Per-state / per-type output layout (data/raw/<state>/).
# Per-type files are written incrementally as each type finishes (crash-safe
# checkpoints). The combined file (_ALL_) is a deduped convenience snapshot.
# clean.py processes the per-type files and SKIPS _ALL_ files to avoid
# double-counting (load_to_db upserts by ads_id, collapsing any overlap).
SCRAPED_TYPE_FILENAME_TEMPLATE = "{state}_{type_id}_{type_slug}_{timestamp}.csv"
SCRAPED_COMBINED_FILENAME_TEMPLATE = "{state}_ALL_{timestamp}.csv"
SCRAPED_COMBINED_MARKER = "_ALL_"

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

# Residential property_type_id -> name (probed 2026-05-29, extended 2026-07-19).
# Each type's total is well under API_OFFSET_CAP, so scraping per type bypasses
# the depth cap. Three non-contiguous blocks, all residential:
#   1-19    whole units      (category_name: Apartment / Condominium, House)
#   41-46   room rentals     (category_name: Room)
#   111-117 houses           (category_name: House)
#
# Excluded — verified commercial via category_name, do NOT re-add:
#   21 Office space, 22 Shop lot, 23 Warehouse/Factory, 24 Others, 25 Retail
#   space, 26 Hotel/Resort, 32 Industrial, 33 Agricultural, 35 Commercial, and
#   27 Sofo / 28 Soho / 29 Sovo — these three read as residential unit types but
#   the API files them under Commercial Property.
# Also excluded: 31 'Residential' and 36 'Mixed Development' — both are Land.
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
    # Room rentals (category_name: Room). Note 44 'Shoplot' is a room inside a
    # shop lot — residential, unlike commercial id 22 'Shop lot'.
    41: "Condo / Services residence / Penthouse / Townhouse",
    42: "Apartment / Flat",
    43: "Houses",
    44: "Shoplot",
    45: "Sharing a house / Flat",
    46: "Others",
    # Houses (category_name: House). 116 and 118+ return nothing.
    111: "Link Bungalow",
    112: "Zero-Lot Bungalow",
    113: "Cluster House",
    114: "Terraced House",
    115: "Twin Villas",
    117: "3.5-storey Terraced House",
}

# Non-residential categories, keyed on the API's category_name (a 5-value closed set).
# Chosen over property_type names: category_name survives Mudah adding new type ids,
# and it correctly keeps room rentals that sit in commercial buildings.
# 'Room' is deliberately NOT excluded — room rentals are in scope.
EXCLUDED_CATEGORIES = frozenset({"Commercial Property", "Land"})

# --- Availability Re-check (recheck.py) ---
# The search API supports a per-listing lookup: GET ?list_id=<id>&fields=all returns
# the item in `data` if live, or an empty `data` array if gone (rented/expired).
# recheck.py uses this to track availability with a decaying check cadence.
RECHECK_DECAY = [(7, 1), (21, 3), (None, 7)]   # (age_days_lt, interval_days); None = catch-all
AD_EXPIRY_FORMAT = "%Y-%m-%d %H:%M:%S"

# Region codes (state URL slug -> Mudah region_id), probed from each state's listing
# page __NEXT_DATA__.initialQuery (one-shot scripts/discover_regions.py, since deleted —
# see git history if these ever need regenerating).
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
