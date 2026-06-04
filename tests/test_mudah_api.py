import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import responses
import config
from scripts import mudah_api


@responses.activate
def test_search_builds_correct_url():
    responses.add(
        responses.GET,
        "https://search.mudah.my/v1/search",
        json={"data": [], "meta": {"total-results": 0, "total-showing": 0}},
        status=200,
    )
    mudah_api.search(region="8", offset=0)
    call = responses.calls[0]
    assert "category=2000" in call.request.url
    assert "type=let" in call.request.url
    assert "region=8" in call.request.url
    assert "from=0" in call.request.url
    assert f"limit={config.API_PAGE_SIZE}" in call.request.url
    assert "fields=all" in call.request.url


@responses.activate
def test_search_includes_property_type_id_when_given():
    responses.add(
        responses.GET,
        "https://search.mudah.my/v1/search",
        json={"data": [], "meta": {"total-results": 0}},
        status=200,
    )
    mudah_api.search(region="8", offset=0, property_type_id=5)
    assert "property_type_id=5" in responses.calls[0].request.url


@responses.activate
def test_search_omits_property_type_id_by_default():
    responses.add(
        responses.GET,
        "https://search.mudah.my/v1/search",
        json={"data": [], "meta": {"total-results": 0}},
        status=200,
    )
    mudah_api.search(region="8", offset=0)
    assert "property_type_id" not in responses.calls[0].request.url


@responses.activate
def test_search_retries_on_429_then_succeeds(monkeypatch):
    monkeypatch.setattr("scripts.mudah_api.time.sleep", lambda _: None)
    responses.add(responses.GET, "https://search.mudah.my/v1/search", status=429)
    responses.add(
        responses.GET,
        "https://search.mudah.my/v1/search",
        json={"data": [{"id": 1, "attributes": {"list_id": 1}}], "meta": {}},
        status=200,
    )
    result = mudah_api.search(region="8", offset=0)
    assert result["data"][0]["attributes"]["list_id"] == 1
    assert len(responses.calls) == 2


@responses.activate
def test_search_retries_on_403_rate_limit(monkeypatch):
    monkeypatch.setattr("scripts.mudah_api.time.sleep", lambda _: None)
    responses.add(responses.GET, "https://search.mudah.my/v1/search", status=403)
    responses.add(
        responses.GET,
        "https://search.mudah.my/v1/search",
        json={"data": [], "meta": {}},
        status=200,
    )
    result = mudah_api.search(region="8", offset=0)
    assert result == {"data": [], "meta": {}}
    assert len(responses.calls) == 2


@responses.activate
def test_search_honors_retry_after_header(monkeypatch):
    waits = []
    monkeypatch.setattr("scripts.mudah_api.time.sleep", lambda s: waits.append(s))
    responses.add(
        responses.GET, "https://search.mudah.my/v1/search",
        status=429, headers={"Retry-After": "7"},
    )
    responses.add(
        responses.GET, "https://search.mudah.my/v1/search",
        json={"data": [], "meta": {}}, status=200,
    )
    mudah_api.search(region="8", offset=0)
    assert waits == [7.0]


@responses.activate
def test_search_raises_after_exhausting_retries(monkeypatch):
    monkeypatch.setattr("scripts.mudah_api.time.sleep", lambda _: None)
    import config
    for _ in range(config.API_MAX_RETRIES + 1):
        responses.add(responses.GET, "https://search.mudah.my/v1/search", status=429)
    with pytest.raises(Exception):
        mudah_api.search(region="8", offset=0)


@responses.activate
def test_search_returns_data_list():
    sample = {
        "data": [{"id": 111, "attributes": {"list_id": 111, "subject": "test"}}],
        "meta": {"total-results": 1, "total-showing": 1},
    }
    responses.add(
        responses.GET,
        "https://search.mudah.my/v1/search",
        json=sample,
        status=200,
    )
    result = mudah_api.search(region="8", offset=0)
    assert result["data"][0]["attributes"]["subject"] == "test"
    assert result["meta"]["total-results"] == 1


@responses.activate
def test_iter_listings_paginates_until_exhausted(monkeypatch):
    monkeypatch.setattr("scripts.mudah_api.time.sleep", lambda _: None)
    n = config.API_PAGE_SIZE
    page1 = {
        "data": [{"id": i, "attributes": {"list_id": i}} for i in range(n)],
        "meta": {"total-results": n + 6, "total-showing": n},
    }
    page2 = {
        "data": [{"id": i, "attributes": {"list_id": i}} for i in range(n, n + 6)],
        "meta": {"total-results": n + 6, "total-showing": 6},
    }
    responses.add(responses.GET, "https://search.mudah.my/v1/search", json=page1, status=200)
    responses.add(responses.GET, "https://search.mudah.my/v1/search", json=page2, status=200)

    items = list(mudah_api.iter_listings(region="8", max_pages=10))
    assert len(items) == n + 6
    assert items[0]["attributes"]["list_id"] == 0
    assert items[-1]["attributes"]["list_id"] == n + 5


@responses.activate
def test_iter_listings_respects_max_pages(monkeypatch):
    monkeypatch.setattr("scripts.mudah_api.time.sleep", lambda _: None)
    n = config.API_PAGE_SIZE
    page = {
        "data": [{"id": i, "attributes": {"list_id": i}} for i in range(n)],
        "meta": {"total-results": 1000, "total-showing": n},
    }
    responses.add(responses.GET, "https://search.mudah.my/v1/search", json=page, status=200)
    responses.add(responses.GET, "https://search.mudah.my/v1/search", json=page, status=200)

    items = list(mudah_api.iter_listings(region="8", max_pages=2))
    assert len(items) == 2 * n


def test_to_csv_row_maps_all_fields():
    api_item = {
        "id": 111945973,
        "attributes": {
            "list_id": 111945973,
            "price_label": "RM 2,000",
            "monthly_rent": 2000,
            "property_type_name": "Service Residence",
            "category_name": "Apartment / Condominium",
            "region_name": "Selangor",
            "subarea_name": "Shah Alam",
            "building_name": "Hill10 Residence",
            "rooms_name": "2",
            "bathroom_name": "1",
            "size": "719",
            "size_suffix": "sq.ft.",
            "published_date": "2026-05-02 20:10:31",
            "adview_url": "https://www.mudah.my/...",
        },
    }
    row = mudah_api.to_csv_row(api_item)
    assert row["ads_id"] == "111945973"
    assert row["monthly_rent"] == "RM 2,000 per month"
    assert row["property_type"] == "Service Residence"
    assert row["category_id"] == "Apartment / Condominium, For rent"
    assert row["state"] == "Selangor"
    assert row["region"] == "Shah Alam"
    assert row["rooms"] == "2"
    assert row["bathroom"] == "1"
    assert row["size"] == "719 sq.ft."
    assert row["address"] == "Hill10 Residence, Shah Alam, Selangor"
    assert row["publishedDatetime"] == "2026-05-02 20:10:31"
    assert row["adviewUrl"] == "https://www.mudah.my/..."


def test_to_csv_row_handles_missing_optional_fields():
    api_item = {
        "id": 999,
        "attributes": {
            "list_id": 999,
            "region_name": "Selangor",
        },
    }
    row = mudah_api.to_csv_row(api_item)
    assert row["ads_id"] == "999"
    assert row["state"] == "Selangor"
    assert row["address"] == "Selangor"


@responses.activate
def test_lookup_returns_item_for_live_listing():
    responses.add(
        responses.GET,
        "https://search.mudah.my/v1/search",
        json={"data": [{"attributes": {"list_id": 114685409}}], "meta": {}},
        status=200,
    )
    data = mudah_api.lookup(114685409)
    assert len(data) == 1
    assert "list_id=114685409" in responses.calls[0].request.url


@responses.activate
def test_lookup_returns_empty_for_gone_listing():
    responses.add(
        responses.GET,
        "https://search.mudah.my/v1/search",
        json={"data": [], "meta": {}},
        status=200,
    )
    assert mudah_api.lookup(999999999) == []


@responses.activate
def test_lookup_retries_on_403(monkeypatch):
    monkeypatch.setattr("scripts.mudah_api.time.sleep", lambda _: None)
    responses.add(responses.GET, "https://search.mudah.my/v1/search", status=403)
    responses.add(
        responses.GET,
        "https://search.mudah.my/v1/search",
        json={"data": [], "meta": {}},
        status=200,
    )
    assert mudah_api.lookup(1) == []
    assert len(responses.calls) == 2


def test_geocode_query_skips_empty_parts():
    a = {"building_name": "", "subarea_name": "Shah Alam", "region_name": "Selangor"}
    assert mudah_api.geocode_query(a) == "Shah Alam, Selangor, Malaysia"


def test_geocode_query_includes_building_when_present():
    a = {"building_name": "Hill10 Residence", "subarea_name": "Shah Alam", "region_name": "Selangor"}
    assert mudah_api.geocode_query(a) == "Hill10 Residence, Shah Alam, Selangor, Malaysia"


def test_geocode_query_handles_all_empty():
    assert mudah_api.geocode_query({}) == ""
