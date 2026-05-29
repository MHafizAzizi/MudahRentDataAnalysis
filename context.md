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

- Created `context.md` and `CLAUDE.md` for session continuity.
- **Task 1 done** — Fixed `backfill_geocode.py:33`: `_geocode_query` → `_geocode`, call site on line 62 updated to match.
- **Task 2 done** — Fixed `mudah_api.py:76`: address no longer starts with `", "` when `building_name` is empty. Updated existing test that was asserting the broken format.
- **Task 3a done** — Simplified `create_mapping_dict` in `2_clean.py`: replaced manual `isna` checks with `dropna`, unified split loop.
- **Task 3b done** — Added skip-guard in `clean_raw_files`: skips files where processed output already exists.
- **Task 5 done** — Removed `indent=2` from `_save_geocache` in `1_webscrape.py`.
- **Streamlit removed** — Deleted `app/` directory, removed `streamlit` and `plotly` from `requirements.txt`, scrubbed all references from `README.md`.
- Added `responses>=0.25` to `requirements.txt` (was missing, required by tests).
- All 33 tests pass.

---

## Pending Tasks

No pending tasks. All known optimisation tasks are complete and Streamlit has been removed.

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
