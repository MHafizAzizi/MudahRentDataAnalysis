import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import responses
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
    assert "fields=all" in call.request.url


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
    page1 = {
        "data": [{"id": i, "attributes": {"list_id": i}} for i in range(24)],
        "meta": {"total-results": 30, "total-showing": 24},
    }
    page2 = {
        "data": [{"id": i, "attributes": {"list_id": i}} for i in range(24, 30)],
        "meta": {"total-results": 30, "total-showing": 6},
    }
    responses.add(responses.GET, "https://search.mudah.my/v1/search", json=page1, status=200)
    responses.add(responses.GET, "https://search.mudah.my/v1/search", json=page2, status=200)

    items = list(mudah_api.iter_listings(region="8", max_pages=10))
    assert len(items) == 30
    assert items[0]["attributes"]["list_id"] == 0
    assert items[29]["attributes"]["list_id"] == 29


@responses.activate
def test_iter_listings_respects_max_pages(monkeypatch):
    monkeypatch.setattr("scripts.mudah_api.time.sleep", lambda _: None)
    page = {
        "data": [{"id": i, "attributes": {"list_id": i}} for i in range(24)],
        "meta": {"total-results": 1000, "total-showing": 24},
    }
    responses.add(responses.GET, "https://search.mudah.my/v1/search", json=page, status=200)
    responses.add(responses.GET, "https://search.mudah.my/v1/search", json=page, status=200)

    items = list(mudah_api.iter_listings(region="8", max_pages=2))
    assert len(items) == 48
