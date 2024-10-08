import requests
import pandas as pd
from bs4 import BeautifulSoup as bs
import json
from tqdm import tqdm
import re
import time
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from datetime import datetime, timedelta

def page_list(state, start, end):
    url = f'https://www.mudah.my/{state}/properties-for-rent?o=' if state else 'https://www.mudah.my/malaysia/properties-for-rent?o='
    page_list = [url + str(i) for i in range(start,end+1)]
    return page_list
#print(page_list('selangor', 1, 2)) #['https://www.mudah.my/selangor/properties-for-rent?o=1', 'https://www.mudah.my/selangor/properties-for-rent?o=2']

def collect_property_links(url):

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0"}
    all_links = []
    response = requests.get(url=url, headers=headers)
    soup = bs(response.text, "html.parser")
    script = soup.find('script', type='application/ld+json')

    if script is not None:
        data = json.loads(script.text)
        item_list = data[2].get('itemListElement', [])
            
        for item in item_list:
            link = item['item']['url']
            all_links.append(link)
    time.sleep(2)
    return all_links
#print(collect_property_links('https://www.mudah.my/selangor/properties-for-rent?o=1')) 

def url_list_per_page(state, start_page, end_page):
    prop_link_list = []
    page_urls = page_list(state, start_page, end_page)
    for page_url in tqdm(page_urls):
        prop_link_list.extend(collect_property_links(page_url))
    return prop_link_list

def get_lat_lon(address):
    geolocator = Nominatim(user_agent="my_agent")
    try:
        location = geolocator.geocode(address)
        if location:
            return location.latitude, location.longitude
        else:
            return None, None
    except (GeocoderTimedOut, GeocoderServiceError):
        time.sleep(2)  # Wait for 2 seconds before retrying
        return get_lat_lon(address)
    
from datetime import datetime, timedelta

def property_detail(state, start_page, end_page, sleep_time):
    test_dict_unit = []
    link = url_list_per_page(state, start_page, end_page)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0"}
   
    # Get the current date and time for scrape_date
    scrape_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for url in tqdm(link):
        try:
            page = requests.get(url=url, headers=headers)
            soup = bs(page.text, 'html.parser')
            script = soup.find('script', id='__NEXT_DATA__')
            if not script:
                script = soup.find('script', type='application/json')
            if script:
                script = script.text
                data = json.loads(script)
            else:
                print(f"Script with id='__NEXT_DATA__' not found for URL: {url}")
                continue
            props = data.get('props', {})
            prop_id_no = re.search(r'-(\d+)\.htm', url).group(1)
            dict_id = [{'realValue': '', 'id': 'ads_id', 'value': prop_id_no, 'label': 'id ads'}]
            details = props.get('initialState', {}).get('adDetails', {}).get('byID', {}).get(prop_id_no, {})
            prop_attr = details.get('attributes', {}).get('propertyParams', [])
            category_attr = details.get('attributes', {}).get('categoryParams', [])
            building_details = prop_attr[2]['params'] if len(prop_attr) > 2 else []
            
            # Extract additional details
            name = details.get('attributes', {}).get("name", "")
            phone = details.get('attributes', {}).get("phone", "")
            description = details.get('attributes', {}).get("body", "")
            state = details.get('attributes', {}).get("regionName", "")
            subregion = details.get('attributes', {}).get("subregionName", "")
            adview_url = details.get('attributes', {}).get("adviewUrl", "")
            
            # Get cCompanyName from store details
            store_id = details.get('relationships', {}).get('store', {}).get('data', {}).get('id')
            c_company_name = props.get('initialState', {}).get('store', {}).get('byID', {}).get(store_id, {}).get('attributes', {}).get('cCompanyName', "")
            
            # Extract publishedDatetime
            published_datetime = details.get('attributes', {}).get("publishedDatetime", "")
            
            # Convert "Yesterday" to actual date
            if "Yesterday" in published_datetime:
                yesterday = datetime.now() - timedelta(days=1)
                time_part = published_datetime.split(" ")[1]
                published_datetime = f"{yesterday.strftime('%Y-%m-%d')} {time_part}"
            elif "Today" in published_datetime:
                today = datetime.now()
                time_part = published_datetime.split(" ")[1]
                published_datetime = f"{today.strftime('%Y-%m-%d')} {time_part}"
            else:
                # If it's already a date, keep it as is
                pass
            
            # Add new fields to the property attributes
            other_attr = [
                {'realValue': name, 'id': 'name', 'value': name, 'label': 'name'},
                {'realValue': phone, 'id': 'phone', 'value': phone, 'label': 'phone'},
                {'realValue': description, 'id': 'body', 'value': description, 'label': 'body'},
                {'realValue': state, 'id': 'state', 'value': state, 'label': 'regionName'},
                {'realValue': subregion, 'id': 'region', 'value': subregion, 'label': 'subregionName'},
                {'realValue': adview_url, 'id': 'adviewUrl', 'value': adview_url, 'label': 'adviewUrl'},
                {'realValue': c_company_name, 'id': 'cCompanyName', 'value': c_company_name, 'label': 'cCompanyName'},
                {'realValue': published_datetime, 'id': 'publishedDatetime', 'value': published_datetime, 'label': 'publishedDatetime'},
                {'realValue': scrape_date, 'id': 'scrape_date', 'value': scrape_date, 'label': 'scrape_date'}
            ]
            
            prop_unit = category_attr + building_details + dict_id + other_attr

            # Check if the category_id is not 'Commercial Property, For rent' or 'Land, For rent'
            category_id = next((item['value'] for item in prop_unit if item['id'] == 'category_id'), None)
            if category_id not in ['Commercial Property, For rent', 'Land, For rent']:
                # Get the address
                address = next((item['value'] for item in prop_unit if item['id'] == 'address'), None)

                # Get latitude and longitude
                lat, lon = get_lat_lon(address) if address else (None, None)

                # Add latitude and longitude to prop_unit
                prop_unit.extend([
                    {'realValue': lat, 'id': 'latitude', 'value': lat, 'label': 'latitude'},
                    {'realValue': lon, 'id': 'longitude', 'value': lon, 'label': 'longitude'}
                ])

                if prop_unit:
                    test_dict_unit.append(prop_unit)
            else:
                print(f"Skipping property with category_id: {category_id}")

        except Exception as e:
            print(f"An error occurred for URL: {url}, error: {e}")
            continue
        time.sleep(sleep_time)
   
    prop_attr = {'prop_name',
                #'location',
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
                 'developer_name',
                 'propage',
                 'name',
                 'adviewUrl',
                 'latitude',
                 'longitude',
                 'publishedDatetime',
                 'scrape_date',
                 'ads_id'
                 }
    data = [{item['id']: item['value'] for item in sublist if item['id'] in prop_attr} for sublist in test_dict_unit]
    df = pd.DataFrame(data)
    return df

state = input("Enter the state you want to scrape: ")
start_page = int(input("Enter the starting page number: "))
end_page = int(input("Enter the ending page number: "))
sleep_time = int(input("Enter the sleep time between requests (in seconds): "))
date = pd.Timestamp.now().strftime("%Y%m%d%H%M%S")

# Execute the scraping process with user inputs
df = property_detail(state, start_page, end_page, sleep_time)
df.to_csv(f'C:/Users/User/Downloads/Jupyter File/Mudah Scrape/Scraped Data/Page{start_page}to{end_page}({date})({state}).csv', index=False)
print("Data has been successfully scraped and saved to CSV file.") #4-5s


#labuan 4, pahang 26, perlis 3, putrajaya 19, ganu 9