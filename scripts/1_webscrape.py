import sys
from pathlib import Path

# Add project root to path for config import
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from scripts.logger import get_logger

logger = get_logger("webscrape")

import cloudscraper
import pandas as pd
from bs4 import BeautifulSoup
import json
from tqdm import tqdm
import re
import random
import time
import requests
from typing import List, Dict, Tuple, Optional, Set
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from datetime import datetime, timedelta

_GEOLOCATOR = Nominatim(
    user_agent=config.GEOLOCATOR_USER_AGENT,
    timeout=config.GEOLOCATION_TIMEOUT
)


def _load_geocache() -> dict:
    if config.GEO_CACHE_FILE.exists():
        with open(config.GEO_CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_geocache(cache: dict) -> None:
    with open(config.GEO_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

# Initialize scraper from config
SCRAPER = cloudscraper.create_scraper(
    browser={
        'browser': config.SCRAPER_CONFIG['browser'],
        'platform': config.SCRAPER_CONFIG['platform'],
        'mobile': config.SCRAPER_CONFIG['mobile']
    },
    delay=config.SCRAPER_CONFIG['delay']
)

# Use config attributes
PROPERTY_ATTRIBUTES = config.PROPERTY_ATTRIBUTES
BASE_URL = config.BASE_URL

def generate_page_urls(state: str, start: int, end: int) -> List[str]:
    """Generate a list of URLs for the given state and page range."""
    # Handle case where state might be empty or None for Malaysia-wide search
    if state:
        base_search_url = f'{BASE_URL}/{state.lower()}/properties-for-rent?o='
    else:
        base_search_url = f'{BASE_URL}/malaysia/properties-for-rent?o='
    # Ensure start and end are valid page numbers (Mudah pages seem to start at 1)
    start = max(1, start)
    end = max(start, end)
    return [f'{base_search_url}{i}' for i in range(start, end + 1)]

def collect_property_links(url: str, min_delay: float = None, max_delay: float = None) -> List[str]:
    """
    Collect property links from a given page URL using the <a> tag method,
    with randomized delays.

    Args:
        url (str): The URL of the search results page to scrape.
        min_delay (float): Minimum delay in seconds before the request (default from config).
        max_delay (float): Maximum delay in seconds before the request (default from config).

    Returns:
        List[str]: List of unique collected property URLs found on the page.
    """
    if min_delay is None:
        min_delay = config.MIN_DELAY
    if max_delay is None:
        max_delay = config.MAX_DELAY

    logger.info(f"Collecting links from: {url}")
    listing_urls: Set[str] = set()

    try:
        delay = random.uniform(min_delay, max_delay)
        logger.debug(f"Waiting {delay:.2f}s before request...")
        time.sleep(delay)

        response = SCRAPER.get(url)
        response.raise_for_status()
        logger.info(f"Fetched {url} (Status: {response.status_code})")

        soup = BeautifulSoup(response.text, 'html.parser')
        potential_links = soup.find_all('a', attrs={'data-listid': True, 'href': True})
        logger.debug(f"Found {len(potential_links)} potential links with data-listid.")

        count = 0
        for link in potential_links:
            href = link.get('href')
            if href and href.startswith(BASE_URL) and '.htm' in href:
                if href not in listing_urls:
                    listing_urls.add(href)
                    count += 1

        logger.info(f"Added {count} unique listing URLs from this page.")

    except cloudscraper.exceptions.CloudflareChallengeError as e:
        logger.error(f"Cloudflare challenge for {url}: {e}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error for {url}: {e}")
    except Exception as e:
        logger.error(f"Error collecting links from {url}: {type(e).__name__} - {e}")

    # Convert the set to a list before returning
    return list(listing_urls)

def get_property_links(state: str, start_page: int, end_page: int) -> List[str]:
    """Get all property links for the given state and page range."""
    page_urls = generate_page_urls(state, start_page, end_page)
    prop_link_list = []
    for page_url in tqdm(page_urls, desc="Collecting property links"):
        prop_link_list.extend(collect_property_links(page_url))
    return prop_link_list

def extract_property_details(url: str, prop_id_no: str, details: Dict) -> List[Dict]:
    """Extract property details from the JSON data."""
    prop_attr = details.get('attributes', {}).get('propertyParams', [])
    category_attr = details.get('attributes', {}).get('categoryParams', [])
    building_details = prop_attr[2]['params'] if len(prop_attr) > 2 else []
    
    # Extract additional details
    attributes = details.get('attributes', {})
    other_attr = [
        {'id': 'name', 'value': attributes.get("name", "")},
        {'id': 'phone', 'value': attributes.get("phone", "")},
        {'id': 'body', 'value': attributes.get("body", "")},
        {'id': 'state', 'value': attributes.get("regionName", "")},
        {'id': 'region', 'value': attributes.get("subregionName", "")},
        {'id': 'adviewUrl', 'value': attributes.get("adviewUrl", "")},
        {'id': 'publishedDatetime', 'value': parse_datetime(attributes.get("publishedDatetime", ""))},
        {'id': 'scrape_date', 'value': datetime.now().strftime("%Y-%m-%d")},
        {'id': 'ads_id', 'value': prop_id_no}
    ]
    
    return category_attr + building_details + other_attr

def get_lat_lon(address: str, cache: dict, retries: int = 3) -> Tuple[Optional[float], Optional[float]]:
    """Get latitude and longitude for a given address, with cache and retry limit."""
    if address in cache:
        return tuple(cache[address])

    for attempt in range(retries):
        try:
            time.sleep(1)  # Respect Nominatim rate limit (1 req/sec)
            location = _GEOLOCATOR.geocode(address)
            result = (location.latitude, location.longitude) if location else (None, None)
            if result != (None, None):
                cache[address] = list(result)
                _save_geocache(cache)
            return result
        except (GeocoderTimedOut, GeocoderServiceError):
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))  # Exponential backoff
            else:
                return (None, None)

def parse_datetime(datetime_str: str) -> str:
    """Parse datetime string and return a standardized format."""
    if not datetime_str:
        return ""
        
    if "Yesterday" in datetime_str:
        date = datetime.now() - timedelta(days=1)
    elif "Today" in datetime_str:
        date = datetime.now()
    else:
        return datetime_str  # Assuming it's already in the correct format

    time_part = datetime_str.split(" ")[1]
    return f"{date.strftime('%Y-%m-%d')} {time_part}"

def scrape_property_details(state: str, start_page: int, end_page: int, sleep_time: int = None) -> pd.DataFrame:
    """Scrape property details for the given state and page range."""
    if sleep_time is None:
        sleep_time = config.BASE_SLEEP_TIME

    geocache = _load_geocache()
    property_data = []
    links = get_property_links(state, start_page, end_page)

    for url in tqdm(links, desc="Scraping..."):
        try:
            actual_delay = sleep_time + random.uniform(0, 2)
            time.sleep(actual_delay)

            page = SCRAPER.get(url)
            page.raise_for_status()
            soup = BeautifulSoup(page.text, 'html.parser')
            script = soup.find('script', id='__NEXT_DATA__') or soup.find('script', type='application/json')

            if not script:
                logger.warning(f"Script tag not found for URL: {url}")
                continue

            data = json.loads(script.text)
            prop_id_match = re.search(r'-(\d+)\.htm', url)

            if not prop_id_match:
                logger.warning(f"Could not extract property ID from URL: {url}")
                continue

            prop_id_no = prop_id_match.group(1)
            details = data.get('props', {}).get('initialState', {}).get('adDetails', {}).get('byID', {}).get(prop_id_no, {})

            if not details:
                logger.warning(f"No details found for property ID: {prop_id_no} at {url}")
                continue

            prop_unit = extract_property_details(url, prop_id_no, details)

            category_id = next((item['value'] for item in prop_unit if item['id'] == 'category_id'), None)
            if category_id not in config.EXCLUDED_CATEGORIES:
                address = next((item['value'] for item in prop_unit if item['id'] == 'address'), None)
                lat, lon = get_lat_lon(address, geocache) if address else (None, None)
                prop_unit.extend([
                    {'id': 'latitude', 'value': lat},
                    {'id': 'longitude', 'value': lon}
                ])
                property_data.append({item['id']: item['value'] for item in prop_unit if item['id'] in PROPERTY_ATTRIBUTES})
            else:
                logger.info(f"Skipping {category_id}")

        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")

    return pd.DataFrame(property_data)

def main():
    state = input("Enter the state you want to scrape (or leave blank for Malaysia-wide): ")
    start_page = int(input("Enter the starting page number: "))
    end_page = int(input("Enter the ending page number: "))
    sleep_time_input = input("Enter the sleep time between requests in seconds (leave blank for default): ")
    sleep_time = int(sleep_time_input) if sleep_time_input else None

    df = scrape_property_details(state, start_page, end_page, sleep_time)

    date = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = config.SCRAPED_DATA_FILENAME_TEMPLATE.format(
        start=start_page,
        end=end_page,
        timestamp=date,
        state=state or "malaysia"
    )
    output_path = config.RAW_DATA_DIR / filename
    df.to_csv(output_path, index=False)
    logger.info(f"Saved {len(df)} rows to {output_path}")

if __name__ == "__main__":
    main()
