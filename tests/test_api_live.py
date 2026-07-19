"""Live API smoke test — detects Mudah schema drift.

Skipped by default (it hits the real network). Run before a scrape with:

    MUDAH_LIVE_TEST=1 pytest tests/test_api_live.py -v        # bash
    $env:MUDAH_LIVE_TEST=1; pytest tests/test_api_live.py -v  # PowerShell

If a field name changed upstream, this fails loudly instead of letting a
corrupted scrape land in the DB.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import config
from scripts import mudah_api

pytestmark = pytest.mark.skipif(
    not os.environ.get("MUDAH_LIVE_TEST"),
    reason="Live API test; set MUDAH_LIVE_TEST=1 to run",
)

# Fields the transformer (to_csv_row / geocode_query) and downstream code rely on.
# Checked across the whole page, not per-item: many are optional on any single
# listing, but a field that's renamed/removed upstream vanishes from ALL items.
#
# NOT included: furnished_name, facilities_name, additional_facilities_name, body.
# The search endpoint never returns these (verified 2026-05-29) — they live only
# on the listing detail page. to_csv_row emits empty strings for them.
_REQUIRED_ATTRS = {
    "list_id", "monthly_rent", "price_label", "property_type_name",
    "property_type_id", "category_name", "region_name", "subarea_name",
    "rooms_name", "bathroom_name", "size", "adview_url", "ad_expiry", "date",
}


def test_live_response_has_expected_shape():
    region = config.REGION_CODES["selangor"]
    body = mudah_api.search(region=region, offset=0)

    assert "data" in body and "meta" in body, "top-level keys changed"
    assert body["meta"].get("total-results", 0) > 0, "no results — query params may have changed"

    items = body["data"]
    assert items, "empty data array on first page"

    # A required field must appear on at least one listing in the page.
    seen = set()
    for item in items:
        seen.update(item.get("attributes", {}).keys())
    missing = _REQUIRED_ATTRS - seen
    assert not missing, f"API response missing expected fields across page: {sorted(missing)}"


def test_live_property_type_filter_works():
    """property_type_id must actually filter — this is our depth-cap workaround."""
    region = config.REGION_CODES["selangor"]
    unfiltered = mudah_api.search(region=region, offset=0)["meta"]["total-results"]
    filtered = mudah_api.search(region=region, offset=0, property_type_id=1)["meta"]["total-results"]
    assert 0 < filtered < unfiltered, (
        f"property_type_id filter not narrowing results "
        f"(filtered={filtered}, unfiltered={unfiltered})"
    )


def test_live_configured_types_are_residential():
    """Every configured type id must still return a residential category.

    Mudah can reassign ids. If one drifts into Commercial Property or Land,
    clean.py would silently discard everything scraped under it — a scrape that
    looks fine but loads nothing. Samples a few ids per block to stay polite.
    """
    region = config.REGION_CODES["selangor"]
    sampled = [1, 13, 41, 44, 46, 113, 114]  # whole-unit, room, and house blocks
    for pid in sampled:
        assert pid in config.RESIDENTIAL_PROPERTY_TYPE_IDS, f"id {pid} left config"
        items = mudah_api.search(region=region, offset=0, property_type_id=pid)["data"]
        if not items:
            continue  # sparse type in this region; not a drift signal
        category = items[0].get("attributes", {}).get("category_name")
        assert category not in config.EXCLUDED_CATEGORIES, (
            f"property_type_id {pid} now returns category {category!r} — "
            f"clean.py would drop everything scraped under it"
        )


def test_live_transformer_maps_real_item():
    region = config.REGION_CODES["selangor"]
    item = mudah_api.search(region=region, offset=0)["data"][0]
    row = mudah_api.to_csv_row(item)
    assert row["ads_id"], "ads_id empty"
    assert row["state"], "state empty"
    assert not row["address"].startswith(", "), "address has leading comma"
