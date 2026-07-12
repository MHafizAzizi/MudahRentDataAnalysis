import sqlite3
from datetime import date

import pytest


class TestDueForCheck:
    TODAY = date(2026, 6, 1)

    def test_never_checked_is_due(self, recheck_module):
        assert recheck_module.due_for_check("2026-05-30", None, self.TODAY) is True

    def test_young_listing_checked_today_not_due(self, recheck_module):
        # age 2 days -> daily interval; checked today -> not due
        assert recheck_module.due_for_check("2026-05-30", "2026-06-01", self.TODAY) is False

    def test_young_listing_checked_yesterday_is_due(self, recheck_module):
        # age 2 days -> daily; last check 1 day ago -> due
        assert recheck_module.due_for_check("2026-05-30", "2026-05-31", self.TODAY) is True

    def test_mid_age_uses_3day_interval(self, recheck_module):
        # first_seen 10 days ago -> 7<=age<21 -> every 3 days
        fs = "2026-05-22"
        assert recheck_module.due_for_check(fs, "2026-05-30", self.TODAY) is False  # 2 days ago
        assert recheck_module.due_for_check(fs, "2026-05-29", self.TODAY) is True   # 3 days ago

    def test_old_listing_uses_weekly_interval(self, recheck_module):
        # first_seen 40 days ago -> weekly
        fs = "2026-04-22"
        assert recheck_module.due_for_check(fs, "2026-05-27", self.TODAY) is False  # 5 days ago
        assert recheck_module.due_for_check(fs, "2026-05-25", self.TODAY) is True   # 7 days ago

    def test_missing_first_seen_treated_as_young(self, recheck_module):
        assert recheck_module.due_for_check(None, "2026-06-01", self.TODAY) is False
        assert recheck_module.due_for_check(None, "2026-05-31", self.TODAY) is True


class TestClassifyGone:
    TODAY = date(2026, 6, 1)

    def test_gone_before_expiry_is_rented(self, recheck_module):
        assert recheck_module.classify_gone("2026-07-07 18:42:56", self.TODAY) == "rented"

    def test_gone_after_expiry_is_expired(self, recheck_module):
        assert recheck_module.classify_gone("2026-05-20 10:00:00", self.TODAY) == "expired"

    def test_missing_expiry_defaults_expired(self, recheck_module):
        assert recheck_module.classify_gone(None, self.TODAY) == "expired"
        assert recheck_module.classify_gone("", self.TODAY) == "expired"

    def test_unparseable_expiry_defaults_expired(self, recheck_module):
        assert recheck_module.classify_gone("not-a-date", self.TODAY) == "expired"


class TestRecheckIntegration:
    @pytest.fixture
    def db(self, tmp_path, load_module, monkeypatch):
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        conn.execute(load_module.CREATE_TABLE_SQL)
        # one active listing that will be found gone (no last_checked -> due),
        # one that will still be alive.
        conn.execute(
            "INSERT INTO properties (ads_id, ad_expiry, first_seen, availability_status, check_count) "
            "VALUES ('gone1', '2099-01-01 00:00:00', '2026-05-30', 'active', 0)"
        )
        conn.execute(
            "INSERT INTO properties (ads_id, first_seen, availability_status, check_count) "
            "VALUES ('alive1', '2026-05-30', 'active', 0)"
        )
        # a terminal one that must be skipped
        conn.execute(
            "INSERT INTO properties (ads_id, availability_status, check_count) "
            "VALUES ('rented1', 'rented', 3)"
        )
        conn.commit()
        conn.close()
        monkeypatch.setattr(__import__("config"), "DB_FILE", db_path)
        return db_path

    def test_recheck_marks_gone_and_alive(self, db, recheck_module, monkeypatch):
        monkeypatch.setattr("scripts.recheck.time.sleep", lambda _: None)

        def fake_lookup(list_id):
            return [] if str(list_id) == "gone1" else [{"attributes": {"list_id": list_id}}]

        monkeypatch.setattr(recheck_module.mudah_api, "lookup", fake_lookup)
        recheck_module.recheck()

        conn = sqlite3.connect(db)
        rows = dict(
            (r[0], r[1:])
            for r in conn.execute(
                "SELECT ads_id, availability_status, gone_at, check_count FROM properties"
            )
        )
        conn.close()

        # gone1: future expiry -> rented, gone_at set, count incremented
        assert rows["gone1"][0] == "rented"
        assert rows["gone1"][1] is not None
        assert rows["gone1"][2] == 1
        # alive1: still active, count incremented, no gone_at
        assert rows["alive1"][0] == "active"
        assert rows["alive1"][1] is None
        assert rows["alive1"][2] == 1
        # rented1: terminal, untouched
        assert rows["rented1"][2] == 3
