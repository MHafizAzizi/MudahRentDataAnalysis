"""Mudah search API client."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import config
import requests
import time
import random
from typing import Dict, Iterator, Optional

# Status codes worth retrying: 429 (rate limit), 403 (Mudah's rate-limit response), 5xx
_RETRYABLE = {403, 429, 500, 502, 503, 504}


def _retry_wait(resp: Optional[requests.Response], attempt: int) -> float:
    """Seconds to wait before the next attempt. Honors Retry-After when present."""
    if resp is not None:
        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            try:
                return min(float(retry_after), config.API_RETRY_MAX_WAIT)
            except ValueError:
                pass
    return min(config.API_BACKOFF_BASE * (2 ** attempt), config.API_RETRY_MAX_WAIT)


def _get_json(params: Dict) -> Dict:
    """GET the search endpoint with the given params, retrying rate limits / 5xx.

    Honors Retry-After and exponential backoff. Returns the parsed JSON body.
    """
    headers = {"User-Agent": config.API_USER_AGENT}
    for attempt in range(config.API_MAX_RETRIES + 1):
        resp = requests.get(
            config.API_BASE_URL,
            params=params,
            timeout=config.API_REQUEST_TIMEOUT,
            headers=headers,
        )
        if resp.status_code in _RETRYABLE and attempt < config.API_MAX_RETRIES:
            time.sleep(_retry_wait(resp, attempt))
            continue
        resp.raise_for_status()
        return resp.json()


def search(region: str, offset: int = 0, property_type_id: Optional[int] = None) -> Dict:
    """Call Mudah search API for one page of rental property listings.

    Pass property_type_id to filter by type (each type has its own depth window,
    which is how we get past API_OFFSET_CAP). Returns {"data": [...], "meta": {...}}.
    Retries on rate limiting / transient errors with backoff.
    """
    params = {
        "category": config.API_CATEGORY_PROPERTY,
        "type": config.API_TYPE_RENT,
        "region": region,
        "from": offset,
        "fields": config.API_FIELDS,
    }
    if property_type_id is not None:
        params["property_type_id"] = str(property_type_id)

    return _get_json(params)


def lookup(list_id) -> list:
    """Return the API `data` list for a single listing id.

    The search endpoint serves a per-listing lookup via `list_id`: a live listing
    comes back as a 1-item `data` array; a gone (rented/expired) listing comes back
    as an empty `data` array. Used by recheck.py as a cheap liveness probe.
    """
    body = _get_json({"list_id": str(list_id), "fields": config.API_FIELDS})
    return body.get("data", [])


def iter_listings(
    region: str,
    start_page: int = 1,
    max_pages: int = 100,
    property_type_id: Optional[int] = None,
) -> Iterator[Dict]:
    """Yield listing dicts for the given region, paginating up to max_pages.

    Stops early when the API returns fewer than API_PAGE_SIZE items.
    """
    page = start_page
    while page <= start_page + max_pages - 1:
        offset = (page - 1) * config.API_PAGE_SIZE
        body = search(region=region, offset=offset, property_type_id=property_type_id)
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
        "subject": _join(a.get("subject")),
        "monthly_rent": monthly_rent,
        "property_type": _join(a.get("property_type_name")),
        "property_type_id": str(a.get("property_type_id", "")),
        "category_id": category_id,
        "state": _join(a.get("region_name")),
        "region": _join(a.get("subarea_name")),
        "subarea_id": str(a.get("subarea_id", "")),
        "building_id": str(a.get("building_id", "")),
        "rooms": _join(a.get("rooms_name")),
        "bathroom": _join(a.get("bathroom_name")),
        "size": size_str,
        "furnished": _join(a.get("furnished_name")),
        "facilities": _join(a.get("facilities_name")),
        "additional_facilities": _join(a.get("additional_facilities_name")),
        "body": _join(a.get("body")),
        "address": address,
        "seller_name": _join(a.get("name")),
        "company_ad": str(a.get("company_ad", "")),
        "ad_seller_type": str(a.get("ad_seller_type", "")),
        "store_verified": _join(a.get("store_verified")),
        "ad_expiry": _join(a.get("ad_expiry")),
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
