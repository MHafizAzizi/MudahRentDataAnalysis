# Project Context — Mudah Rent Analysis

> **Living document.** Updated at the end of every session. Start every new session by reading this file before doing anything else.

---

## What This Project Is

A data pipeline that pulls Malaysian rental listings from the **Mudah.my public JSON search API**, cleans them, and stores them in SQLite.

- Replaces the original HTML scraper (~25× faster, no Cloudflare issues)
- Geocodes listings via Nominatim, cached in `data/geocache.json`
- Pipeline: `1_webscrape.py` → `2_clean.py` → `3_load_to_db.py`

---

## Current Branch

`main`. PRs #17 and #18 merged. No active feature branches.

---

## What Was Decided

- Use Mudah's undocumented JSON search API (`search.mudah.my/v1/search`) instead of HTML parsing.
- Geocode using only `building_name + subarea_name + region_name` (no street address from API). Precision is region-level — acceptable for state/region analytics.
- Geocode cache stored as `data/geocache.json` — shared between scraper and backfill script.
- `discover_regions.py` is a one-shot script; `REGION_CODES` are hardcoded in `config.py`.
- `backfill_geocode.py` loads `1_webscrape.py` via `importlib` (because the filename starts with a digit).
- Tests use the `responses` library to mock HTTP — no network required.
- `mapping.csv` drives property-type standardisation via `create_mapping_dict` in `2_clean.py`.
- Dropped 6 columns (`furnished`, `facilities`, `additional_facilities`, `body`, `subject`, `building_id`) and deleted `enrich_details.py` — detail-only fields no longer collected.

---

## API Facts (discovered 2026-05-29, via live probe)

- **Depth cap:** the search API returns an empty `data` array at offset ≥ ~9,984, regardless of `total-results`. Stored as `config.API_OFFSET_CAP`. Selangor reports 36,393 total but only ~9,960 are reachable in a single unfiltered query.
- **Workaround:** filter by `property_type_id` — every residential type's total is well under the cap (largest: Service Residence ≈ 5,754). `scrape_all_types()` loops all residential types for full coverage. See `config.RESIDENTIAL_PROPERTY_TYPE_IDS`.
- **Filter param name:** `property_type_id` (1=Condominium, 2=Apartment, 5=Service Residence, …). Commercial types 21–24 (Office, Shop lot, Warehouse) deliberately excluded.
- **Page size:** page returns 24 by default but honors `limit` up to 200 (`limit=300` → truncates to 24; `size=` ignored). `config.API_PAGE_SIZE = 200`; `search()` sends explicit `limit`.
- **`ad_expiry` field EXISTS** in the response, format `'YYYY-MM-DD HH:MM:SS'` (≈ 39-day window). Captured into schema; drives `recheck.py`'s rented-vs-expired classification.
- **Per-listing lookup:** `GET ?list_id=<id>&fields=all` returns a 1-item `data` array if live, empty if gone. Cheap, Cloudflare-free liveness check — basis for `recheck.py` (`mudah_api.lookup`). Batching ids does NOT work.
- **Rate limiting:** rapid requests return HTTP 403 (not 429). `search()`/`lookup()` retry 403/429/5xx with backoff + `Retry-After`.
- **KNOWN GAP:** the search endpoint does **not** return `furnished`, `facilities`, `additional_facilities`, or `body` — they live only on the listing detail page HTML. These columns were dropped (no longer collected).

---

## Pending Tasks

- **Schedule `recheck.py`** periodically (e.g. cron) so availability data accrues over time. (Not wired into `run_pipeline.py`.)
- **Backfill `ad_expiry`** for the ~45k legacy rows that predate the field (they classify as `expired` when gone, since expiry is unknown).
- **Faster recheck — `scripts/bulk_recheck.py` (not built).** Current `recheck.py` does a per-listing `lookup()` sequentially (~28–34h for all ~102k active). Proposed rescrape-diff:
  1. Run `scrape_all_types()` for all 16 states → fresh `ads_id` set (~2–4h).
  2. DB active ids NOT in fresh set → `lookup()` to confirm gone + classify via `ad_expiry` (only the delta, ~10% = ~9k calls).
  3. DB active ids IN fresh set → bulk `UPDATE last_checked_at` (no per-listing API calls).
  Result: ~3–6h total. Reuses `scrape_all_types()` + `mudah_api.lookup()` unchanged.

**Deprioritized / ignored:**
- Kedah avg rent anomaly (RM3,999 vs national RM2,493) — likely commercial listings inflating the mean. User chose to ignore.

---

## Key Files

| File | Role |
|---|---|
| `config.py` | Paths, API constants, `REGION_CODES` |
| `scripts/mudah_api.py` | API client (`search`, `lookup`, `iter_listings`, `to_csv_row`, `geocode_query`) |
| `scripts/1_webscrape.py` | Orchestrator: API → geocode → CSV. Interactive: `_prompt_state` + `_prompt_property_types` pickers |
| `scripts/2_clean.py` | Cleans raw CSVs → processed CSVs (`clean_rent`/`clean_size`/`clean_rooms`) |
| `scripts/3_load_to_db.py` | ON CONFLICT upsert → SQLite; `ensure_schema()` migrates older DBs |
| `scripts/backfill_geocode.py` | Backfills NULL lat/lon in DB using region-level geocoding |
| `scripts/recheck.py` | Optional: availability tracking (active/rented/expired) via per-listing API lookup |
| `scripts/discover_regions.py` | One-shot: enumerate Mudah region IDs |
| `tests/test_mudah_api.py` | API client + transformer tests (HTTP mocked) |
| `tests/test_clean.py` | Cleaning function tests |
| `data/geocache.json` | Geocode cache (query → lat/lon) |
| `data/mudah_rent.db` | SQLite database (table `properties`, ~102k rows) |

---

## How to Update This File

At the end of each session:
- Record what changed under a dated **Last Session** note (keep it short; git history holds detail).
- Update **Pending Tasks** — remove completed items, add newly discovered ones.
- Leave other sections intact unless a decision was reversed or context changed.

---

## Last Session — 2026-06-06

- `rooms` normalized: `clean_rooms()` added to `2_clean.py`; DB backfilled (13,100 `.0` rows → int). Tests 27 passed.
- Geocode backfill run → 0 null lat/lon across ~102k rows.
- Housekeeping: deleted merged local branches, 81MB coldrop backup, and regenerable junk (logs, `data/archived`, `data/old`, caches).
- recheck.py timing measured (~28–34h full run); not run.
- context.md trimmed (removed accumulated What Changed log + completed tasks).
