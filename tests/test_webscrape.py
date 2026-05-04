import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import config


def _make_db(path: Path, ads_ids: list[str]) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE properties (ads_id TEXT PRIMARY KEY)")
    conn.executemany("INSERT INTO properties VALUES (?)", [(i,) for i in ads_ids])
    conn.commit()
    conn.close()


SAMPLE_URLS = [
    "https://www.mudah.my/kuala-lumpur/apartment-111.htm",
    "https://www.mudah.my/kuala-lumpur/apartment-222.htm",
    "https://www.mudah.my/kuala-lumpur/apartment-333.htm",
]


class TestLoadKnownAdsIds:
    def test_no_db_returns_empty_set(self, webscrape_module, monkeypatch, tmp_path):
        monkeypatch.setattr(config, "DB_FILE", tmp_path / "nonexistent.db")
        assert webscrape_module._load_known_ads_ids() == set()

    def test_empty_table_returns_empty_set(self, webscrape_module, monkeypatch, tmp_path):
        db_path = tmp_path / "test.db"
        _make_db(db_path, [])
        monkeypatch.setattr(config, "DB_FILE", db_path)
        monkeypatch.setattr(config, "DB_TABLE", "properties")
        assert webscrape_module._load_known_ads_ids() == set()

    def test_returns_all_ids(self, webscrape_module, monkeypatch, tmp_path):
        db_path = tmp_path / "test.db"
        _make_db(db_path, ["111", "222", "333"])
        monkeypatch.setattr(config, "DB_FILE", db_path)
        monkeypatch.setattr(config, "DB_TABLE", "properties")
        assert webscrape_module._load_known_ads_ids() == {"111", "222", "333"}

    def test_corrupt_db_returns_empty_set(self, webscrape_module, monkeypatch, tmp_path):
        db_path = tmp_path / "corrupt.db"
        db_path.write_bytes(b"not a sqlite file")
        monkeypatch.setattr(config, "DB_FILE", db_path)
        monkeypatch.setattr(config, "DB_TABLE", "properties")
        assert webscrape_module._load_known_ads_ids() == set()


class TestScrapeFiltering:
    def _mock_response(self):
        resp = MagicMock()
        resp.text = "<html></html>"  # no __NEXT_DATA__ → loop continues without processing
        resp.raise_for_status = MagicMock()
        return resp

    def _patch_common(self, webscrape_module, monkeypatch, tmp_path, known_ids):
        db_path = tmp_path / "test.db"
        _make_db(db_path, known_ids)
        monkeypatch.setattr(config, "DB_FILE", db_path)
        monkeypatch.setattr(config, "DB_TABLE", "properties")
        monkeypatch.setattr(webscrape_module, "get_property_links", lambda *a, **kw: list(SAMPLE_URLS))
        monkeypatch.setattr(webscrape_module, "_load_geocache", lambda: {})
        monkeypatch.setattr(webscrape_module.time, "sleep", lambda x: None)
        mock_get = MagicMock(return_value=self._mock_response())
        monkeypatch.setattr(webscrape_module.SCRAPER, "get", mock_get)
        return mock_get

    def test_known_listings_skipped(self, webscrape_module, monkeypatch, tmp_path):
        mock_get = self._patch_common(webscrape_module, monkeypatch, tmp_path, ["111", "222"])
        webscrape_module.scrape_property_details("kuala-lumpur", 1, 1, sleep_time=0)
        assert mock_get.call_count == 1
        assert "333" in mock_get.call_args[0][0]

    def test_skip_known_false_fetches_all(self, webscrape_module, monkeypatch, tmp_path):
        mock_get = self._patch_common(webscrape_module, monkeypatch, tmp_path, ["111", "222"])
        webscrape_module.scrape_property_details("kuala-lumpur", 1, 1, sleep_time=0, skip_known=False)
        assert mock_get.call_count == 3

    def test_empty_db_fetches_all(self, webscrape_module, monkeypatch, tmp_path):
        mock_get = self._patch_common(webscrape_module, monkeypatch, tmp_path, [])
        webscrape_module.scrape_property_details("kuala-lumpur", 1, 1, sleep_time=0)
        assert mock_get.call_count == 3

    def test_all_known_fetches_none(self, webscrape_module, monkeypatch, tmp_path):
        mock_get = self._patch_common(webscrape_module, monkeypatch, tmp_path, ["111", "222", "333"])
        webscrape_module.scrape_property_details("kuala-lumpur", 1, 1, sleep_time=0)
        assert mock_get.call_count == 0
