# Project Context — Mudah Rent Analysis

> **Living document.** Updated at the end of every session. Start every new session by reading this file before doing anything else.

---

## What This Project Is

A data pipeline that pulls Malaysian rental listings from the **Mudah.my public JSON search API**, cleans them, and stores them in SQLite.

- Replaces the original HTML scraper (~25× faster, no Cloudflare issues)
- Geocodes listings via Nominatim, cached in `data/geocache.json`
- Pipeline: `scrape.py` → `clean.py` → `load_to_db.py`

---

## Current Branch

`main`. PRs #17, #18, #20, #21 merged.

---

## What Was Decided

- Use Mudah's undocumented JSON search API (`search.mudah.my/v1/search`) instead of HTML parsing.
- Geocode using only `building_name + subarea_name + region_name` (no street address from API). Precision is region-level — acceptable for state/region analytics.
- Geocode cache stored as `data/geocache.json` — shared between scraper and backfill script.
- `REGION_CODES` are hardcoded in `config.py`; the one-shot `discover_regions.py` that generated them was deleted (2026-07-12 audit) — recover from git history if IDs ever rotate.
- Pipeline scripts use plain names (`scrape.py`, `clean.py`, `load_to_db.py`) and normal imports — the numbered filenames and their `importlib` loading dance were removed in the 2026-07-12 audit.
- Tests use the `responses` library to mock HTTP — no network required.
- `mapping.csv` drives property-type standardisation via `create_mapping_dict` in `clean.py`.
- Dropped 6 columns (`furnished`, `facilities`, `additional_facilities`, `body`, `subject`, `building_id`) and deleted `enrich_details.py` — detail-only fields no longer collected.
- **Non-residential listings excluded on `category_name`, not `property_type`** (2026-07-19). `config.EXCLUDED_CATEGORIES = {"Commercial Property", "Land"}`; `clean.py` drops them at ingest. Room rentals deliberately KEPT (user decision). Rationale: type names don't partition cleanly — `Shop lot` is commercial but `Shoplot` rooms are residential, and ids 31/36 are named `Residential`/`Mixed Development` yet return vacant land. `category_name` is a closed 5-value set (`Apartment / Condominium`, `House`, `Room`, `Commercial Property`, `Land`) and survives Mudah adding type ids. A `property_type`-name deny-list was tried first and caught only 5,577 of 11,152 non-residential rows.

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

- **Delete disk junk** (blocked by tool permissions 2026-07-19): `data/old/` (26 MB) + `logs/*.log` — regenerable, gitignored. `Remove-Item -Recurse -Force data\old; Remove-Item logs\*.log`.

- **Room-rental coverage gap.** Ids 27–29, 41–46, 113 (`category_name: Room`) are not in `RESIDENTIAL_PROPERTY_TYPE_IDS`, so the scraper never requests them; the ~6.1k rows in the DB arrived via API leakage and are not representative. Rooms are in scope by decision, so either add those ids to config for real coverage, or treat the existing Room rows as unreliable and analyze them separately. Do not mix them into whole-unit rent averages (Room avg RM546 vs RM2,335 for apartments).
- **Drift canary:** if CPI `Other`'s average rent jumps well above ~RM2,900, a new non-residential category is leaking in — re-run the type-id probe.

**Resolved:**
- ~~Kedah avg rent anomaly~~ — SOLVED 2026-07-19. Was commercial contamination (Kulim/Sungai Petani industrial corridor: 852 warehouse listings at RM500k–755k/mo on a small residential base). Kedah median was always RM1,300; the mean was pure outlier artifact. Now RM1,564 after the category filter.

---

## Key Files

| File | Role |
|---|---|
| `config.py` | Paths, API constants, `REGION_CODES` |
| `scripts/mudah_api.py` | API client (`search`, `lookup`, `iter_listings`, `to_csv_row`, `geocode_query`) |
| `scripts/scrape.py` | Orchestrator: API → geocode → CSV. Interactive: `_prompt_state` + `_prompt_property_types` pickers |
| `scripts/clean.py` | Cleans raw CSVs → processed CSVs (`clean_rent`/`clean_size`/`clean_rooms`) |
| `scripts/load_to_db.py` | ON CONFLICT upsert → SQLite; `ensure_schema()` migrates older DBs |
| `scripts/backfill_geocode.py` | Backfills NULL lat/lon in DB using region-level geocoding |
| `scripts/recheck.py` | Optional: availability tracking (active/rented/expired) via per-listing API lookup |
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

## Last Session — 2026-07-19 (part 2)

Investigated the Kedah rent anomaly (previously deprioritized). Root cause: commercial listings, not a code bug. Fixed on branch `chore/exclude-commercial`.

**API probe (live, ids 1–49 + 113 across 4 regions).** Authoritative findings:
- Residential ids 1–19 match `RESIDENTIAL_PROPERTY_TYPE_IDS` exactly. Good.
- Commercial: 21 Office space, 22 Shop lot, 23 Warehouse/Factory, 25 Retail space, 26 Hotel/Resort, 32 Industrial, 33 Agricultural, 35 Commercial.
- **Land** masquerades as residential: id 31 = `Residential`, id 36 = `Mixed Development`, both `category_name: Land`.
- **Room rentals are a separate id block** (27–29 Sofo/Soho/Sovo, 41–46, 113) NOT in config — the scraper never requests them, yet ~6.1k arrived via API cross-type leakage. Coverage is therefore partial/unrepresentative.
- Confirms the API leaks types you didn't ask for; `property_type_id` filtering is not a hard guarantee.

**Applied:** `EXCLUDED_CATEGORIES` in config; one-line filter in `clean.py:clean_rental_data`; one test (asserts Room survives — guards the explicit decision). One-shot `DELETE` removed 11,152 rows (10,628 Commercial Property + 524 Land). DB 144,874 → 133,722 rows. Backup at `data/mudah_rent.db.bak`. Tests 73 passed, 3 skipped.

**Corrected stats** (national avg RM4,159 → **RM2,509**). Kedah RM15,053 → **RM1,564**, now 10th of 16 — anomaly fully resolved, no longer a data-quality concern. Top: Putrajaya RM5,440, Sabah RM3,771, Penang RM3,133. Bottom: Perlis RM1,060, Kelantan RM1,076.

## Earlier — 2026-07-19 (part 1)

Second ponytail audit applied (branch `chore/ponytail-cuts`, PR → `main`). Net −40 lines; tests 72 passed, 3 skipped (baseline held).
- Dropped dead page-range plumbing: `scrape(state, max_pages=500, ...)` and `iter_listings(region, max_pages, ...)` — no more `start_page`/`end_page` (every caller started at page 1). `scrape_all_types` also lost `write_files` (writes unconditional).
- Deleted write-only `check_count` DB column from schema, upsert, and recheck updates. Existing DB keeps orphan column (harmless — `ensure_schema` only ADDs).
- `logger.py` is now config-only (`basicConfig`); callers do `import scripts.logger` + `logging.getLogger(name)` — `get_logger` wrapper deleted.
- Deleted conftest module fixtures (`clean_module` etc.) — tests import `from scripts import ...` directly.
- Inlined one-use constants: `DATETIME_FORMAT` (→ clean.py literal), `RECHECK_TERMINAL_STATUSES` (→ literal `NOT IN ('rented','expired')` in recheck query).
- `_prompt_state` returns `Optional[str]` (was 1-item list).
- README updated (iter_listings signature, recheck columns).
- Audit finding NOT applied (permission-blocked, left to user): delete `data/old/` (26 MB stale CSVs) + `logs/*.log` (1.9 MB) — regenerable, gitignored junk.

## Earlier — 2026-07-12

Ponytail audit applied, then committed and pushed as PR #20 (`testing` → `main`). Tests: 72 passed, 3 skipped.
- Renamed `1_webscrape.py`/`2_clean.py`/`3_load_to_db.py` → `scrape.py`/`clean.py`/`load_to_db.py`; replaced all `importlib` loaders (run_pipeline, recheck, backfill_geocode, conftest) with plain imports.
- Deleted `discover_regions.py` (one-shot, already ran) and dropped its deps `cloudscraper` + `beautifulsoup4`; also dropped redundant `numpy` pin (pandas dependency).
- Deleted dead HTML-scraper config (`BASE_URL`, `SCRAPER_CONFIG`, `MIN_DELAY`/`MAX_DELAY`/`BASE_SLEEP_TIME`, `PROPERTY_ATTRIBUTES`, `EXCLUDED_CATEGORIES`) and `SCRAPED_DATA_FILENAME_TEMPLATE`.
- Removed `--pages` mode from `run_pipeline.py` (all-types is the only scrape mode; `--state`/`--skip-scrape` remain).
- `load_to_db.py` now deletes loaded raw/processed CSVs instead of archiving to `data/archived/` + `data/old/raw/` (dirs + config vars removed — DB is the source of truth).
- Shrunk `logger.py` to a `logging.basicConfig` one-shot (single INFO level; no DEBUG calls existed).
- Removed `ensure_recheck_columns` alias and an unused `shutil` import.
- README updated to match. Tests: 72 passed, 3 skipped (same as baseline).

## Earlier — 2026-06-12

- `run_pipeline.py` reworked: default is now **all states + all types**.
  - `--state` defaults to `all` (loops `sorted(config.REGION_CODES)`); pass a slug for one state.
  - All-types scrape (`scrape_all_types` per state) is the default mode. Old `--all-types` flag removed.
  - Page-range scraping moved behind `--pages` flag (single state only; manual CSV write restored since `scrape()` returns a DataFrame and does not write).
- Added `run_pipeline.bat` (project root): double-click → full default run; `%*` passes through CLI overrides. Ends with `pause` so the window stays open.
- Verified `run_pipeline.py --help` parses clean.
- Created personal skill `context-creation` (`C:\Users\USER\.claude\skills\context-creation\SKILL.md`) — generalizes this project's CLAUDE.md → context.md living-doc pattern for all projects. Built TDD-style (baseline + verification subagent tests passed). Not part of this repo.

## Earlier — 2026-06-06

- `rooms` normalized: `clean_rooms()` added to `2_clean.py`; DB backfilled (13,100 `.0` rows → int). Tests 27 passed.
- Geocode backfill run → 0 null lat/lon across ~102k rows.
- Housekeeping: deleted merged local branches, 81MB coldrop backup, and regenerable junk (logs, `data/archived`, `data/old`, caches).
- recheck.py timing measured (~28–34h full run); not run.
- context.md trimmed (removed accumulated What Changed log + completed tasks).
