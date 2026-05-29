# Project Context — Mudah Rent Analysis

> **Living document.** Updated at the end of every session. Start every new session by reading this file before doing anything else.

---

## What This Project Is

A data pipeline that pulls Malaysian rental listings from the **Mudah.my public JSON search API**, cleans them, stores them in SQLite, and visualises them via a Streamlit dashboard.

- Replaces the original HTML scraper (~25× faster, no Cloudflare issues)
- Geocodes listings via Nominatim, cached in `data/geocache.json`
- Pipeline: `1_webscrape.py` → `2_clean.py` → `3_load_to_db.py` → `app/Streamlit.py`

---

## Current Branch

`feat/api-scraper` — API-based scraper rewrite. Not yet merged to `main`.

---

## What Was Decided

- Use Mudah's undocumented JSON search API (`search.mudah.my/v1/search`) instead of HTML parsing.
- Geocode using only `building_name + subarea_name + region_name` (no street address from API). Precision is region-level — acceptable for state/region analytics.
- Geocode cache stored as `data/geocache.json` — shared between scraper and backfill script.
- `discover_regions.py` is a one-shot script; `REGION_CODES` are hardcoded in `config.py`.
- `backfill_geocode.py` loads `1_webscrape.py` via `importlib` (because the filename starts with a digit).
- Tests use the `responses` library to mock HTTP — no network required.
- `mapping.csv` drives property-type standardisation via `create_mapping_dict` in `2_clean.py`.

---

## API Facts (discovered 2026-05-29, via live probe)

- **Depth cap:** the search API returns an empty `data` array at offset ≥ ~9,984, regardless of `total-results`. Stored as `config.API_OFFSET_CAP`. Selangor reports 36,393 total but only ~9,960 are reachable in a single unfiltered query.
- **Workaround:** filter by `property_type_id` — every residential type's total is well under the cap (largest: Service Residence ≈ 5,754). `scrape_all_types()` loops all residential types for full coverage. See `config.RESIDENTIAL_PROPERTY_TYPE_IDS`.
- **Filter param name:** `property_type_id` (1=Condominium, 2=Apartment, 5=Service Residence, …). Commercial types 21–24 (Office, Shop lot, Warehouse) deliberately excluded.
- **`ad_expiry` field EXISTS** in the response (e.g. posted 2026-05-29, expires 2026-07-30 ≈ 62-day window). Not yet captured into the schema — enables sold/expired inference if a recheck step is added.
- **Rate limiting:** rapid requests return HTTP 403 (not 429). `mudah_api.search()` now retries 403/429/5xx with backoff + `Retry-After`.
- **KNOWN GAP:** the search endpoint does **not** return `furnished`, `facilities`, `additional_facilities`, or `body` — these come back empty on every listing (verified across pages), despite the README's claim. They live only on the listing detail page. Capturing them would require a detail-page enrichment step (not yet built).

## What Changed (Last Session — 2026-05-29)

- **Detail-API probe (done)** — Confirmed NO dedicated detail JSON API exists. `?list_id=X` returns a stripped 200 with no furnishing data; `/v1/listing|listings|ad/X` all 404/410; `ad.mudah.my` host doesn't exist. Detail-only fields are recoverable ONLY from the listing detail page HTML.
- **`scripts/enrich_details.py` (new)** — Optional backfill for `furnished` / `facilities` / `additional_facilities` / `body`. Fetches each row's `adviewUrl` via `cloudscraper`, parses `props.initialState.adDetails.byID.<list_id>.attributes` from `__NEXT_DATA__`. `furnished`/`facilities`/`additional_facilities` come from the `categoryParams` array (keyed by `id`); `body` is a top-level attribute. Selects DB rows with an `adviewUrl` but missing any enrich field. `--limit N` for test runs. NOT wired into `run_pipeline.py`.
- **Config** — Added `ENRICH_FIELDS`, `ENRICH_MIN_DELAY` (2.0), `ENRICH_MAX_DELAY` (5.0), `ENRICH_REQUEST_TIMEOUT` (30).
- **Tests** — Added `tests/test_enrich.py` (parser + url-id extraction, 7 tests, HTML mocked) and `enrich_module` fixture in `conftest.py`.
- **Docs** — README: documented enrich step, folder structure, the detail-page note. context.md updated.
- 46 passed, 3 skipped (live API tests, gated by `MUDAH_LIVE_TEST=1`).

### Earlier this session (pre-compaction)
- Created `context.md` + `CLAUDE.md`; removed Streamlit (`app/`, deps, README refs).
- `mudah_api.py`: retry/backoff with `Retry-After` (403/429/5xx), `property_type_id` param, 9 new fields in `to_csv_row` (subject, property_type_id, subarea_id, building_id, seller_name, company_ad, ad_seller_type, store_verified, ad_expiry — image_count excluded), address-prefix fix.
- `config.py`: `API_USER_AGENT`, `API_MAX_RETRIES`, `API_BACKOFF_BASE`, `API_RETRY_MAX_WAIT`, `API_OFFSET_CAP=9984`, `RESIDENTIAL_PROPERTY_TYPE_IDS`.
- `1_webscrape.py`: `scrape_all_types()` loops residential types to bypass depth cap; compact geocache write.
- `run_pipeline.py`: `--all-types` flag.
- `3_load_to_db.py`: schema + db_cols expanded to 29 columns; added `idx_ad_expiry`, `idx_property_type_id`.
- `tests/test_load.py`: `in_memory_conn` now uses `load_module.CREATE_TABLE_SQL` (no schema drift). Added `tests/test_api_live.py` (live smoke test). `responses>=0.25` added to requirements.

---

## Pending Tasks

Applied recommendations from `F:\Coding\CarData\docs\HANDOVER_PROPERTIES.md`. Done this session:
- Retry/backoff with `Retry-After` in `mudah_api.search()`.
- `property_type_id` filtering + `scrape_all_types()` to bypass the depth cap.
- Live schema-drift smoke test (`tests/test_api_live.py`, gated by `MUDAH_LIVE_TEST=1`).

Still pending (deferred from the handover):
- **`recheck.py`** — availability tracking with a decay policy (daily → 3-day → weekly → stop). Would use the `ad_expiry` field to distinguish rented-early vs expired. Requires `last_checked_at` / `availability_status` columns.

Done since last update:
- **Detail-page enrichment** — DONE. `scripts/enrich_details.py` recovers `furnished` / `facilities` / `additional_facilities` / `body` from detail-page HTML (search API omits them). Optional backfill pass.
- **Capture `ad_expiry`** into schema — DONE (added to `to_csv_row` + DB schema).

---

## Key Files

| File | Role |
|---|---|
| `config.py` | Paths, API constants, `REGION_CODES` |
| `scripts/mudah_api.py` | API client (`search`, `iter_listings`, `to_csv_row`, `geocode_query`) |
| `scripts/1_webscrape.py` | Orchestrator: API → geocode → CSV |
| `scripts/2_clean.py` | Cleans raw CSVs → processed CSVs |
| `scripts/3_load_to_db.py` | Upserts processed CSVs → SQLite |
| `scripts/backfill_geocode.py` | Backfills NULL lat/lon in DB using region-level geocoding |
| `scripts/enrich_details.py` | Optional backfill: furnished/facilities/additional_facilities/body from detail-page HTML |
| `scripts/discover_regions.py` | One-shot: enumerate Mudah region IDs |
| `tests/test_mudah_api.py` | API client + transformer tests (HTTP mocked) |
| `tests/test_clean.py` | Cleaning function tests |
| `data/geocache.json` | Geocode cache (query → lat/lon) |
| `data/mudah_rent.db` | SQLite database |
| `.claude/worktrees/.../plans/2026-05-07-optimisations.md` | Full implementation plan with code snippets |

---

## How to Update This File

At the end of each session, update the following sections:
- **What Changed** — replace with a summary of this session's changes (date + what was done).
- **Pending Tasks** — check off completed tasks; add any new ones discovered.
- Leave all other sections intact unless a decision was reversed or context changed.
