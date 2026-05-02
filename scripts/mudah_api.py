"""Mudah search API client."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import config
import requests
from typing import Dict


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
