"""
Single-command pipeline runner for Mudah Rent Analysis.

Usage:
    # Default: scrape ALL states, ALL residential types, then clean + load
    python run_pipeline.py

    # One state, all types
    python run_pipeline.py --state selangor

    # Skip scraping (clean + load only — reprocess existing raw files)
    python run_pipeline.py --skip-scrape
"""

import argparse
import sys
import time
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
import config
from scripts import scrape, clean, load_to_db


def step(label: str):
    print(f"\n{'='*50}")
    print(f"  {label}")
    print(f"{'='*50}")


def main():
    parser = argparse.ArgumentParser(description="Run Mudah Rent Analysis pipeline")
    parser.add_argument("--state", required=False, default="all",
                        help="State URL slug (e.g. 'selangor'), or 'all' for every state. Default: all.")
    parser.add_argument("--skip-scrape", action="store_true", help="Skip scraping, run clean+load only")
    args = parser.parse_args()

    start_time = time.time()

    if not args.skip_scrape:
        step("STEP 1: Scraping")
        # scrape_all_types writes per-type checkpoints + a combined CSV
        # under data/raw/<state>/ as it goes.
        states = sorted(config.REGION_CODES) if args.state == "all" else [args.state]

        total_rows = 0
        for i, state in enumerate(states, 1):
            print(f"\n[{i}/{len(states)}] Scraping state: {state}")
            df = scrape.scrape_all_types(state)
            total_rows += len(df)
            print(f"  {state}: {len(df)} unique rows")
        print(f"\nScraped {total_rows} total unique rows across {len(states)} state(s).")
    else:
        print("Skipping scrape step.")

    step("STEP 2: Cleaning")
    clean.clean_raw_files()

    step("STEP 3: Loading to database")
    load_to_db.load_processed_files()

    elapsed = time.time() - start_time
    print(f"\nPipeline complete in {elapsed:.1f}s. DB: {config.DB_FILE}")


if __name__ == "__main__":
    main()
