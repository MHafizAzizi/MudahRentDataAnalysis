import cloudscraper
import pandas as pd
from bs4 import BeautifulSoup
import json
from tqdm import tqdm
import re
import random
import time
from typing import List, Dict, Tuple, Optional
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from datetime import datetime, timedelta

# Constants
BASE_URL = 'https://www.mudah.my'
SCRAPER = cloudscraper.create_scraper(
    browser={
        'browser': 'firefox',
        'platform': 'windows',
        'mobile': False
    },
    delay=10
)
PROPERTY_ATTRIBUTES = {
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
    'ads_id',
    # 'adviewUrl'
}

def generate_page_urls(state: str, start: int, end: int) -> List[str]:
    """Generate a list of URLs for the given state and page range."""
    base_url = f'{BASE_URL}/{state}/properties-for-rent?o=' if state else f'{BASE_URL}/malaysia/properties-for-rent?o='
    return [f'{base_url}{i}' for i in range(start, end + 1)]

def collect_property_links(url: str, min_delay: float = 3, max_delay: float = 7) -> List[str]:
    """
    Collect property links from a given page URL with randomized delays.
    
    Args:
        url (str): The URL to scrape
        min_delay (float): Minimum delay in seconds (default: 3)
        max_delay (float): Maximum delay in seconds (default: 7)
    
    Returns:
        List[str]: List of collected property URLs
    """
    try:
        # Random delay before making the request
        delay = random.uniform(min_delay, max_delay)
        time.sleep(delay)
        
        response = SCRAPER.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        script = soup.find('script', type='application/ld+json')
        all_links = []
        
        if script:
            data = json.loads(script.text)
            item_list = data[2].get('itemListElement', [])
            all_links = [item['item']['url'] for item in item_list]
        
        return all_links
        
    except json.JSONDecodeError as e:
        print(f"JSON parsing error for {url}: {str(e)}")
        return []
    except Exception as e:
        print(f"Error collecting links from {url}: {str(e)}")
        return []

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

def scrape_property_details(state: str, start_page: int, end_page: int, sleep_time: int) -> pd.DataFrame:
    """Scrape property details for the given state and page range."""
    property_data = []
    links = get_property_links(state, start_page, end_page)

    for url in tqdm(links, desc="Scraping..."):
        try:
            page = SCRAPER.get(url)
            page.raise_for_status()
            soup = BeautifulSoup(page.text, 'html.parser')
            script = soup.find('script', id='__NEXT_DATA__') or soup.find('script', type='application/json')
            
            if not script:
                print(f"Script not found for URL: {url}")
                continue

            data = json.loads(script.text)
            prop_id_no = re.search(r'-(\d+)\.htm', url).group(1)
            details = data.get('props', {}).get('initialState', {}).get('adDetails', {}).get('byID', {}).get(prop_id_no, {})
            
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
        
        time.sleep(sleep_time)

    return pd.DataFrame(property_data)

# Keep the get_lat_lon, parse_datetime, extract_property_details, and main functions unchanged

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
    if "Yesterday" in datetime_str:
        date = datetime.now() - timedelta(days=1)
    elif "Today" in datetime_str:
        date = datetime.now()
    else:
        return datetime_str  # Assuming it's already in the correct format

    time_part = datetime_str.split(" ")[1]
    return f"{date.strftime('%Y-%m-%d')} {time_part}"

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

    