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


def _join(value) -> str:
    """Join list values with ', ', stringify scalar, or '' if missing."""
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


def to_csv_row(item: Dict) -> Dict[str, str]:
    """Map one API listing item to the CSV row schema expected by 2_clean.py / 3_load_to_db.py."""
    a = item.get("attributes", {})

    size = a.get("size", "")
    size_suffix = a.get("size_suffix", "")
    size_str = f"{size} {size_suffix}".strip() if size else ""

    price_label = a.get("price_label", "")
    monthly_rent = f"{price_label} per month" if price_label else ""

    cat = a.get("category_name", "")
    category_id = f"{cat}, For rent" if cat else ""

    _addr_parts = [a.get("building_name") or "", a.get("subarea_name") or "", a.get("region_name") or ""]
    address = ", ".join(p for p in _addr_parts if p.strip())

    return {
        "ads_id": str(a.get("list_id", "")),
        "monthly_rent": monthly_rent,
        "property_type": _join(a.get("property_type_name")),
        "category_id": category_id,
        "state": _join(a.get("region_name")),
        "region": _join(a.get("subarea_name")),
        "rooms": _join(a.get("rooms_name")),
        "bathroom": _join(a.get("bathroom_name")),
        "size": size_str,
        "furnished": _join(a.get("furnished_name")),
        "facilities": _join(a.get("facilities_name")),
        "additional_facilities": _join(a.get("additional_facilities_name")),
        "body": _join(a.get("body")),
        "address": address,
        "publishedDatetime": _join(a.get("published_date") or a.get("date")),
        "adviewUrl": _join(a.get("adview_url")),
    }


def geocode_query(attributes: Dict) -> str:
    """Build a clean comma-separated geocode query from API attributes.

    Skips empty parts. Appends 'Malaysia' when at least one part exists.
    """
    parts = [
        attributes.get("building_name") or "",
        attributes.get("subarea_name") or "",
        attributes.get("region_name") or "",
    ]
    parts = [p.strip() for p in parts if p and p.strip()]
    if not parts:
        return ""
    return ", ".join(parts) + ", Malaysia"
