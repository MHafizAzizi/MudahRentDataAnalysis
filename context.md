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
- **`ad_expiry` field EXISTS** in the response, format `'YYYY-MM-DD HH:MM:SS'` (e.g. posted 2026-05-29, expires 2026-07-07 ≈ 39-day window). Captured into the schema; drives `recheck.py`'s rented-vs-expired classification.
- **Per-listing lookup:** `GET ?list_id=<id>&fields=all` returns the listing as a 1-item `data` array if live, or an empty `data` array if gone (rented/expired). A cheap, Cloudflare-free liveness check — basis for `recheck.py` (`mudah_api.lookup`). Batching multiple ids does NOT work (comma → 1 result, repeated param → 0).
- **Rate limiting:** rapid requests return HTTP 403 (not 429). `mudah_api.search()`/`lookup()` retry 403/429/5xx with backoff + `Retry-After`.
- **KNOWN GAP (now addressed):** the search endpoint does **not** return `furnished`, `facilities`, `additional_facilities`, or `body` — these come back empty on every listing (verified across pages). They live only on the listing detail page HTML. Recovered via the optional `scripts/enrich_details.py` backfill.

## What Changed (Last Session — 2026-05-29, scrape efficiency)

Branch: `feat/scrape-efficiency` (off the CLI-menu work).

- **Page-size bug fixed (~8× fewer API requests).** Live-probed the property search API: a page returns **24 by default but honors `limit` up to 200** (`limit=300` → truncates to 24; `size=` is ignored). `config.API_PAGE_SIZE` was **24** and `search()` sent no `limit`, so it got 24/page while `iter_listings` could have pulled 200 — ~8× more requests than needed. Now:
  - `config.API_PAGE_SIZE = 200`; `mudah_api.search()` sends explicit `limit=API_PAGE_SIZE`.
  - `iter_listings` already keys offset + stop-condition off `API_PAGE_SIZE`, so it's correct (offset steps 0, 200, 400, …).
  - Verified live: `from=0` vs `from=200` return distinct id sets, **overlap=0**.
- **Tests:** added a `limit={API_PAGE_SIZE}` assertion to `test_search_builds_correct_url`; the two `iter_listings` tests hardcoded 24-item pages (would stop after page 1 at the new size) — rewrote them to size pages off `config.API_PAGE_SIZE`. README `API_PAGE_SIZE` row updated to 200. 73 passed, 3 skipped.
- Came out of comparing scrape mechanics with CarData (`F:\Coding\CarData\src\eagle_client.py`), which already used `limit=200`. Other CarData diffs noted but NOT adopted (lower value): cloudscraper + rotating UA to cut 403s; per-page checkpoint + resume. Our client absorbs 403s via retry/backoff instead.

## What Changed (Last Session — 2026-05-29, CLI menus)

- **`1_webscrape.py` interactive CLI redesigned** (CarData-style, modelled on `F:\Coding\CarData\src\scraper.py`):
  - **`_prompt_state()` (new)** — numbered menu of the 16 known states (sorted `REGION_CODES` slugs, 3/row). Accepts a number or a slug.
  - **`_prompt_property_types()` (new)** — numbered menu of the 17 residential types (2/row). Accepts numbers/ranges/combos (`1,3,5` | `1-10` | `1-5,8,12-15`). Enter alone (or no valid token) = ALL types. Returns id list or `None`.
  - **`scrape_all_types()`** — new optional `property_type_ids: Optional[List[int]]` param to scrape a subset; `None` = every residential type (unchanged default).
  - **`main()`** rewritten to use the two pickers; always runs per-type via `scrape_all_types` (pages 1–500). **Dropped** the old y/N + page-range path.
  - **Gotcha:** menu positions ≠ `property_type_id`s (e.g. menu 12-13 → ids 14,15). Selection is by list position, matching CarData.
- **Per-state / per-type CSV output (CarData-style, crash-safe).** Output now lives under `data/raw/<state>/`:
  - `scrape_all_types()` writes **one CSV per property type immediately after that type finishes** (crash-safe checkpoint — a mid-run failure keeps completed types), filename `{state}_{type_id}_{type_slug}_{ts}.csv` via `_slug()` helper. After all types: a deduped combined `{state}_ALL_{ts}.csv`. New `write_files=True` param (set False in tests/programmatic use). `main()` no longer writes — `scrape_all_types` owns all output.
  - **`2_clean.py`** now uses `RAW_DATA_DIR.rglob('*.csv')` (recurse into state subdirs) and **skips `_ALL_` combined files** (per-type files cover every row; `3_load_to_db` upserts by `ads_id` so any cross-type overlap collapses at load). Marker: `config.SCRAPED_COMBINED_MARKER`.
  - **Config** — added `SCRAPED_TYPE_FILENAME_TEMPLATE`, `SCRAPED_COMBINED_FILENAME_TEMPLATE`, `SCRAPED_COMBINED_MARKER`. Old `SCRAPED_DATA_FILENAME_TEMPLATE` kept (unused by `main` now).
- Imports: added `re`, `List`. 73 passed, 3 skipped (no test changes needed — new params backward-compatible). Verified file layout + dedup + clean-discovery via smoke tests.

## What Changed (Earlier — 2026-05-29, cont.)

- **`scripts/recheck.py` (new)** — Availability tracking. Re-checks active listings via `mudah_api.lookup(ads_id)` on a decaying cadence (`config.RECHECK_DECAY`: <7d daily, <21d every 3d, else weekly). Gone listings classified by `ad_expiry` (`classify_gone`): before expiry → `rented`, at/after or missing → `expired`. Maintains in-place columns `first_seen`, `last_checked_at`, `availability_status`, `gone_at`, `check_count`. `--limit N` for test runs. NOT in `run_pipeline.py`. Verified live: migrated the 45k-row legacy DB and correctly flipped 5 stale rows to `expired`.
- **`mudah_api.lookup(list_id)` (new)** — per-listing liveness probe; factored shared retry into `_get_json()`, reused by `search()`.
- **`3_load_to_db.py`** — Added 5 recheck columns to schema. Replaced DELETE-then-append with a real `ON CONFLICT(ads_id)` upsert that refreshes scrape columns + re-affirms `active`/clears `gone_at`/bumps `last_checked_at`, but preserves `first_seen`/`check_count`. New `ensure_schema()` (alias `ensure_recheck_columns`) migrates older DBs by ALTER-adding ANY missing column (driven by `COLUMN_DEFS`) — fixed the legacy DB which also lacked the prior session's added columns. Added `idx_availability_status`.
- **Config** — `RECHECK_DECAY`, `RECHECK_TERMINAL_STATUSES`, `AD_EXPIRY_FORMAT`.
- **Tests** — `tests/test_recheck.py` (decay, classify, in-memory integration), `lookup()` tests in `test_mudah_api.py`, upsert preservation + recheck-default tests in `test_load.py`, `recheck_module` fixture. 62 passed, 3 skipped.

### Earlier this session
- **Detail-API probe** — Confirmed NO dedicated detail JSON API exists. `?list_id=X` returns a stripped 200 with no furnishing data; `/v1/listing|listings|ad/X` all 404/410; `ad.mudah.my` host doesn't exist. Detail-only fields are recoverable ONLY from the listing detail page HTML.
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

All handover recommendations are now implemented. Done:
- **`recheck.py`** — DONE. Availability tracking with decaying cadence + rented-vs-expired classification via `ad_expiry`. Added `first_seen`/`last_checked_at`/`availability_status`/`gone_at`/`check_count` columns.
- **Detail-page enrichment** — DONE. `scripts/enrich_details.py` recovers `furnished` / `facilities` / `additional_facilities` / `body` from detail-page HTML.
- **Capture `ad_expiry`** into schema — DONE.

Possible future work (not requested):
- CLI menus done (state + property-type pickers). If page-range / single-type scraping is ever needed again, `scrape()` still exists — re-expose via a flag.
- Per-state/per-type CSV output done. Crash-safety granularity is per *type* (a crash mid-type loses that type's in-progress rows). Finer (per-page) checkpointing would require pushing writes into `scrape()`.
- Old per-run flat raw CSVs (pre-subdir) still in `data/raw/` root are picked up by `2_clean.py`'s rglob — harmless, but could be archived.
- Schedule `recheck.py` to run periodically (e.g. cron) so availability data accrues over time.
- Backfill `ad_expiry` for the ~45k legacy rows that predate the field (they currently classify as `expired` when gone, since expiry is unknown).
- Wire `enrich_details.py` / `recheck.py` cadence into a single maintenance command if desired.

---

## Key Files

| File | Role |
|---|---|
| `config.py` | Paths, API constants, `REGION_CODES` |
| `scripts/mudah_api.py` | API client (`search`, `lookup`, `iter_listings`, `to_csv_row`, `geocode_query`) |
| `scripts/1_webscrape.py` | Orchestrator: API → geocode → CSV. Interactive: `_prompt_state` + `_prompt_property_types` pickers |
| `scripts/2_clean.py` | Cleans raw CSVs → processed CSVs |
| `scripts/3_load_to_db.py` | ON CONFLICT upsert → SQLite; `ensure_schema()` migrates older DBs |
| `scripts/backfill_geocode.py` | Backfills NULL lat/lon in DB using region-level geocoding |
| `scripts/enrich_details.py` | Optional backfill: furnished/facilities/additional_facilities/body from detail-page HTML |
| `scripts/recheck.py` | Optional: availability tracking (active/rented/expired) via per-listing API lookup |
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
