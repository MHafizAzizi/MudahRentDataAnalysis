"""
Single-command pipeline runner for Mudah Rent Analysis.

Usage:
    # Full pipeline (scrape + clean + load)
    python run_pipeline.py --state selangor --start 1 --end 10

    # Skip scraping (clean + load only — reprocess existing raw files)
    python run_pipeline.py --skip-scrape
"""

import argparse
import importlib.util
import sys
import time
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
import config


def load_script(name: str):
    """Load a numbered script module by filename."""
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def step(label: str):
    print(f"\n{'='*50}")
    print(f"  {label}")
    print(f"{'='*50}")


def main():
    parser = argparse.ArgumentParser(description="Run Mudah Rent Analysis pipeline")
    parser.add_argument("--state", required=False, default="selangor",
                        help="State URL slug (e.g. 'selangor', 'kuala-lumpur'). See config.REGION_CODES.")
    parser.add_argument("--start", type=int, default=1, help="Start page number")
    parser.add_argument("--end", type=int, default=1, help="End page number")
    parser.add_argument("--all-types", action="store_true",
                        help="Scrape every residential property type (full coverage past the ~10k depth cap). Ignores --start/--end.")
    parser.add_argument("--skip-scrape", action="store_true", help="Skip scraping, run clean+load only")
    args = parser.parse_args()

    start_time = time.time()

    if not args.skip_scrape:
        step("STEP 1: Scraping")
        from datetime import datetime
        scraper = load_script(Path("1_webscrape.py"))

        if args.all_types:
            df = scraper.scrape_all_types(state=args.state)
        else:
            df = scraper.scrape(
                state=args.state,
                start_page=args.start,
                end_page=args.end,
            )

        if df.empty:
            print("No data scraped. Exiting.")
            sys.exit(1)

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = config.SCRAPED_DATA_FILENAME_TEMPLATE.format(
            start=args.start,
            end=args.end,
            timestamp=timestamp,
            state=args.state
        )
        output_path = config.RAW_DATA_DIR / filename
        df.to_csv(output_path, index=False)
        print(f"Scraped {len(df)} rows → {output_path}")
    else:
        print("Skipping scrape step.")

    step("STEP 2: Cleaning")
    cleaner = load_script(Path("2_clean.py"))
    cleaner.clean_raw_files()

    step("STEP 3: Loading to database")
    loader = load_script(Path("3_load_to_db.py"))
    loader.load_processed_files()

    elapsed = time.time() - start_time
    print(f"\nPipeline complete in {elapsed:.1f}s. DB: {config.DB_FILE}")


if __name__ == "__main__":
    main()
