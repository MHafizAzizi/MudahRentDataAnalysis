import json
import pytest


def _make_html(by_id: dict) -> str:
    blob = {"props": {"initialState": {"adDetails": {"byID": by_id}}}}
    return (
        '<html><body><script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(blob)
        + "</script></body></html>"
    )


SAMPLE_BY_ID = {
    "114685409": {
        "attributes": {
            "body": "Spacious corner unit.",
            "categoryParams": [
                {"id": "monthly_rent", "value": "RM 2,600 per month"},
                {"id": "furnished", "value": "Fully Furnished"},
                {"id": "facilities", "value": "Pool, Gym, Security"},
                {"id": "additional_facilities", "value": "Air-Cond, Near LRT"},
            ],
        }
    }
}


class TestParseDetail:
    def test_extracts_all_fields(self, enrich_module):
        html = _make_html(SAMPLE_BY_ID)
        out = enrich_module.parse_detail(html, "114685409")
        assert out["furnished"] == "Fully Furnished"
        assert out["facilities"] == "Pool, Gym, Security"
        assert out["additional_facilities"] == "Air-Cond, Near LRT"
        assert out["body"] == "Spacious corner unit."

    def test_missing_fields_default_empty(self, enrich_module):
        html = _make_html({"999": {"attributes": {"categoryParams": []}}})
        out = enrich_module.parse_detail(html, "999")
        assert all(out[f] == "" for f in ("furnished", "facilities", "additional_facilities", "body"))

    def test_falls_back_to_first_ad_when_id_missing(self, enrich_module):
        html = _make_html(SAMPLE_BY_ID)
        out = enrich_module.parse_detail(html, "does-not-match")
        assert out["furnished"] == "Fully Furnished"

    def test_no_next_data_raises(self, enrich_module):
        with pytest.raises(ValueError, match="__NEXT_DATA__"):
            enrich_module.parse_detail("<html>nothing</html>", "1")

    def test_empty_by_id_raises(self, enrich_module):
        with pytest.raises(ValueError, match="byID"):
            enrich_module.parse_detail(_make_html({}), "1")


class TestListIdFromUrl:
    def test_extracts_id(self, enrich_module):
        url = "https://www.mudah.my/some-listing-title-114685409.htm"
        assert enrich_module._list_id_from_url(url) == "114685409"

    def test_no_match_returns_empty(self, enrich_module):
        assert enrich_module._list_id_from_url("https://www.mudah.my/foo") == ""
