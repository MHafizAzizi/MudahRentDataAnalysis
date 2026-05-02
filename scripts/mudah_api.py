"""Mudah search API client."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import config
import requests
import time
import random
from typing import Dict, Iterator


def search(region: str, offset: int = 0) -> Dict:
    """Call Mudah search API for one page of rental property listings.

    Returns the raw JSON: {"data": [...], "meta": {...}}.
    """
    params = {
        "category": config.API_CATEGORY_PROPERTY,
        "type": config.API_TYPE_RENT,
        "region": region,
        "from": offset,
        "fields": config.API_FIELDS,
    }
    r = requests.get(
        config.API_BASE_URL,
        params=params,
        timeout=config.API_REQUEST_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def iter_listings(region: str, start_page: int = 1, max_pages: int = 100) -> Iterator[Dict]:
    """Yield listing dicts for the given region, paginating up to max_pages.

    Stops early when the API returns fewer than API_PAGE_SIZE items.
    """
    page = start_page
    while page <= start_page + max_pages - 1:
        offset = (page - 1) * config.API_PAGE_SIZE
        body = search(region=region, offset=offset)
        items = body.get("data", [])
        for item in items:
            yield item
        if len(items) < config.API_PAGE_SIZE:
            return
        page += 1
        # Polite delay between API calls
        time.sleep(random.uniform(config.API_MIN_DELAY, config.API_MAX_DELAY))
