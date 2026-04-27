"""
Configuration for Mudah Rent Data Analysis project.
"""

from pathlib import Path

# --- Project Paths ---
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
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
}

# Property categories to exclude from scraping
EXCLUDED_CATEGORIES = {
    "Commercial Property, For rent",
    "Land, For rent",
    "Room, For rent"
}

# --- Geolocation Configuration ---
GEOLOCATOR_USER_AGENT = "mudah_rent_analysis/1.0"
GEOLOCATION_TIMEOUT = 5  # seconds

# --- Data Cleaning Configuration ---
# Output filename format for scraped data
SCRAPED_DATA_FILENAME_TEMPLATE = "Scraped_Data_Page{start}to{end}({timestamp})({state}).csv"

# Datetime format for parsing
DATETIME_FORMAT = "%m/%d/%Y"
