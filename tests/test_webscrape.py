import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import config


def _make_db(path: Path, ads_ids: list) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE properties (ads_id TEXT PRIMARY KEY)")
    conn.executemany("INSERT INTO properties VALUES (?)", [(i,) for i in ads_ids])
    conn.commit()
    conn.close()


def _make_item(ads_id: str) -> dict:
    return {"attributes": {"list_id": ads_id}}


SAMPLE_ITEMS = [_make_item("111"), _make_item("222"), _make_item("333")]


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
    def _patch_common(self, webscrape_module, monkeypatch, tmp_path, known_ids):
        db_path = tmp_path / "test.db"
        _make_db(db_path, known_ids)
        monkeypatch.setattr(config, "DB_FILE", db_path)
        monkeypatch.setattr(config, "DB_TABLE", "properties")
        monkeypatch.setattr(config, "REGION_CODES", {"selangor": "9"})

        mock_api = MagicMock()
        mock_api.iter_listings.return_value = iter(list(SAMPLE_ITEMS))
        mock_api.to_csv_row.side_effect = lambda item: {"ads_id": str(item["attributes"]["list_id"])}
        mock_api.geocode_query.return_value = ""
        monkeypatch.setattr(webscrape_module, "mudah_api", mock_api)

        monkeypatch.setattr(webscrape_module, "_load_geocache", lambda: {})
        monkeypatch.setattr(webscrape_module, "_save_geocache", lambda c: None)
        monkeypatch.setattr(webscrape_module, "geocode", lambda q, c: (None, None))

        return mock_api

    def test_known_listings_skipped(self, webscrape_module, monkeypatch, tmp_path):
        mock_api = self._patch_common(webscrape_module, monkeypatch, tmp_path, ["111", "222"])
        webscrape_module.scrape("selangor", 1, 1)
        assert mock_api.to_csv_row.call_count == 1
        assert mock_api.to_csv_row.call_args[0][0]["attributes"]["list_id"] == "333"

    def test_skip_known_false_processes_all(self, webscrape_module, monkeypatch, tmp_path):
        mock_api = self._patch_common(webscrape_module, monkeypatch, tmp_path, ["111", "222"])
        webscrape_module.scrape("selangor", 1, 1, skip_known=False)
        assert mock_api.to_csv_row.call_count == 3

    def test_empty_db_processes_all(self, webscrape_module, monkeypatch, tmp_path):
        mock_api = self._patch_common(webscrape_module, monkeypatch, tmp_path, [])
        webscrape_module.scrape("selangor", 1, 1)
        assert mock_api.to_csv_row.call_count == 3

    def test_all_known_processes_none(self, webscrape_module, monkeypatch, tmp_path):
        mock_api = self._patch_common(webscrape_module, monkeypatch, tmp_path, ["111", "222", "333"])
        webscrape_module.scrape("selangor", 1, 1)
        assert mock_api.to_csv_row.call_count == 0


def test_backfill_imports_without_error():
    """Regression: backfill_geocode previously referenced _geocode_query which doesn't exist."""
    import importlib, sys
    for key in list(sys.modules.keys()):
        if 'backfill' in key:
            del sys.modules[key]
    import scripts.backfill_geocode  # must not raise AttributeError
