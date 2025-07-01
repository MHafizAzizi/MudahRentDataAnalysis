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

# --- Configuration ---
BASE_URL = 'https://www.mudah.my'

# Cloudscraper setup
SCRAPER = cloudscraper.create_scraper(
    browser={
        'browser': 'firefox',
        'platform': 'windows',
        'mobile': False
    },
    delay=10  # General delay for the scraper session
)

# Property attributes to extract
PROPERTY_ATTRIBUTES = {
    # 'name',
    # 'phone',
    'body',
    'address',
    'category_id',
    'monthly_rent',
    'property_type',
    'state',
    'region',
    'rooms',
    'bathroom',
    'size',
    'furnished',
    'facilities',
    'additional_facilities',
    'latitude',
    'longitude',
    'publishedDatetime',
    'scrape_date',
    'ads_id',
    # 'adviewUrl'
}

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

def collect_property_links(url: str, min_delay: float = 3, max_delay: float = 7) -> List[str]:
    """
    Collect property links from a given page URL using the <a> tag method,
    with randomized delays.

    Args:
        url (str): The URL of the search results page to scrape.
        min_delay (float): Minimum delay in seconds before the request (default: 3).
        max_delay (float): Maximum delay in seconds before the request (default: 7).

    Returns:
        List[str]: List of unique collected property URLs found on the page.
    """
    print(f"Attempting to collect links from: {url}")
    listing_urls: Set[str] = set()  # Use a set internally to handle duplicates easily

    try:
        # Random delay before making the request
        delay = random.uniform(min_delay, max_delay)
        print(f"Waiting for {delay:.2f} seconds before request...")
        time.sleep(delay)

        response = SCRAPER.get(url)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        print(f"Successfully fetched {url} (Status: {response.status_code})")

        # Create a BeautifulSoup object
        soup = BeautifulSoup(response.text, 'html.parser')

        # Find all <a> tags that have a 'data-listid' attribute AND an 'href'
        potential_links = soup.find_all(
            'a',
            attrs={
                'data-listid': True,  # Check if the attribute exists
                'href': True          # Check if the attribute exists
            }
        )
        print(f"Found {len(potential_links)} potential links with data-listid.")

        # Filter these links to get only the valid listing URLs
        count = 0
        for link in potential_links:
            href = link.get('href')
            # Check if it's a valid URL starting with the base and looks like a listing page
            if href and href.startswith(BASE_URL) and '.htm' in href:
                # Add the URL to the set (duplicates are ignored automatically)
                if href not in listing_urls:
                    listing_urls.add(href)
                    count += 1

        print(f"Added {count} new unique listing URLs from this page.")

    except cloudscraper.exceptions.CloudflareChallengeError as e:
        print(f"Cloudflare challenge encountered for {url}: {str(e)}")
    except requests.exceptions.RequestException as e:  # Catch requests library errors
        print(f"Network error collecting links from {url}: {str(e)}")
    except Exception as e:
        # Catch other potential errors during parsing or processing
        print(f"Error collecting links from {url}: {type(e).__name__} - {str(e)}")

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

def get_lat_lon(address: str) -> Tuple[Optional[float], Optional[float]]:
    """Get latitude and longitude for a given address."""
    geolocator = Nominatim(user_agent="my_agent")
    try:
        location = geolocator.geocode(address)
        return (location.latitude, location.longitude) if location else (None, None)
    except (GeocoderTimedOut, GeocoderServiceError):
        time.sleep(2)  # Wait for 2 seconds before retrying
        return get_lat_lon(address)

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

def scrape_property_details(state: str, start_page: int, end_page: int, sleep_time: int) -> pd.DataFrame:
    """Scrape property details for the given state and page range."""
    property_data = []
    links = get_property_links(state, start_page, end_page)

    for url in tqdm(links, desc="Scraping..."):
        try:
            # Add random delay with a base sleep time
            actual_delay = sleep_time + random.uniform(0, 2)
            time.sleep(actual_delay)
            
            page = SCRAPER.get(url)
            page.raise_for_status()
            soup = BeautifulSoup(page.text, 'html.parser')
            script = soup.find('script', id='__NEXT_DATA__') or soup.find('script', type='application/json')
            
            if not script:
                print(f"Script not found for URL: {url}")
                continue

            data = json.loads(script.text)
            prop_id_match = re.search(r'-(\d+)\.htm', url)
            
            if not prop_id_match:
                print(f"Could not extract property ID from URL: {url}")
                continue
                
            prop_id_no = prop_id_match.group(1)
            details = data.get('props', {}).get('initialState', {}).get('adDetails', {}).get('byID', {}).get(prop_id_no, {})
            
            if not details:
                print(f"No details found for property ID: {prop_id_no} at URL: {url}")
                continue
                
            prop_unit = extract_property_details(url, prop_id_no, details)
            
            # Check if the category_id is not 'Commercial Property, For rent' or 'Land, For rent'
            category_id = next((item['value'] for item in prop_unit if item['id'] == 'category_id'), None)
            if category_id not in ['Commercial Property, For rent', 'Land, For rent', 'Room, For rent']:
                address = next((item['value'] for item in prop_unit if item['id'] == 'address'), None)
                lat, lon = get_lat_lon(address) if address else (None, None)
                prop_unit.extend([
                    {'id': 'latitude', 'value': lat},
                    {'id': 'longitude', 'value': lon}
                ])
                property_data.append({item['id']: item['value'] for item in prop_unit if item['id'] in PROPERTY_ATTRIBUTES})
            else:
                print(f"Skipping {category_id}")

        except Exception as e:
            print(f"An error occurred for {url}, error: {e}")

    return pd.DataFrame(property_data)

def main():
    state = input("Enter the state you want to scrape: ")
    start_page = int(input("Enter the starting page number: "))
    end_page = int(input("Enter the ending page number: "))
    sleep_time = int(input("Enter the sleep time between requests (in seconds): "))

    df = scrape_property_details(state, start_page, end_page, sleep_time)
    
    date = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f'D:/3. Data Analysis Project/Mudah Website/Mudah Rental Properties/Scraped Data/Scraped_Data_Page{start_page}to{end_page}({date})({state}).csv'
    df.to_csv(filename, index=False)
    print(f"Data has been successfully scraped and saved to {filename}")

if __name__ == "__main__":
    main()
