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

## What Changed (Last Session — 2026-05-29)

- Identified 5 pending tasks from the optimisation plan at `.claude/worktrees/sleepy-archimedes-cd66c6/docs/superpowers/plans/2026-05-07-optimisations.md`
- No code was changed this session — tasks were audited, not implemented.
- Created `context.md` (this file) and `CLAUDE.md` for session continuity.

---

## Pending Tasks

These are **not yet implemented**. Work through them in order — Task 1 is the only crash-level bug.

### Task 1 — CRITICAL BUG: `backfill_geocode.py` broken reference
- **File:** `scripts/backfill_geocode.py:33`
- **Bug:** `_geocode_query = _scraper._geocode_query` — function does not exist on the scraper module. Should be `_scraper.geocode`.
- Also update the call site on line 62: `_geocode_query(q, cache)` → `_geocode(q, cache)`.
- Add regression test in `tests/test_webscrape.py`: import the module and assert no `AttributeError`.

### Task 2 — Address leading-comma bug in `mudah_api.py`
- **File:** `scripts/mudah_api.py:76`
- **Bug:** `address = f"{a.get('building_name', '')}, {a.get('subarea_name', '')}, ..."` produces `", Subang Jaya, Selangor"` when `building_name` is empty.
- **Fix:** filter empty parts before joining:
  ```python
  _addr_parts = [a.get("building_name") or "", a.get("subarea_name") or "", a.get("region_name") or ""]
  address = ", ".join(p for p in _addr_parts if p.strip())
  ```
- Add tests: `test_to_csv_row_address_no_leading_comma` and `test_to_csv_row_address_all_empty`.

### Task 3a — Simplify `create_mapping_dict` in `2_clean.py`
- **File:** `scripts/2_clean.py:56–72`
- Currently uses `iterrows()` with manual `isna` checks. Replace with `dropna` + same loop — removes dead code. The mapping CSV is tiny so vectorisation isn't the goal; clarity is.

### Task 3b — Skip-guard for already-processed files in `2_clean.py`
- **File:** `scripts/2_clean.py:84`
- Re-cleans raw files even if a processed output already exists. Add a guard:
  ```python
  out_path = config.PROCESSED_DATA_DIR / raw_path.name
  if out_path.exists():
      logger.info(f"Already processed, skipping: {raw_path.name}")
      continue
  ```

### Task 4 — Streamlit optimisations in `app/Streamlit.py`
- **File:** `app/Streamlit.py`
- (a) `load_data` uses `SELECT *` — loads unused `body` column. Replace with explicit column list (see plan for `_DB_COLS`).
- (b) Add `ttl=3600` to `@st.cache_data` on `load_data`.
- (c) Cache `total_prop_by_type()` and `total_prop_by_state()` with `@st.cache_data` — they recompute on every Streamlit render cycle.
- No unit tests — verify manually with `streamlit run app/Streamlit.py`.

### Task 5 — Compact geocache JSON
- **File:** `scripts/1_webscrape.py:46`
- Change `json.dump(cache, f, ensure_ascii=False, indent=2)` → remove `indent=2` for compact output.
- Trivial; no test change needed.

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
| `scripts/discover_regions.py` | One-shot: enumerate Mudah region IDs |
| `app/Streamlit.py` | Dashboard (reads from SQLite) |
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
