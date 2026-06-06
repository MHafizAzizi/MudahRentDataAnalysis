import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from scripts.logger import get_logger

logger = get_logger("clean")

import pandas as pd
import numpy as np
import shutil


def clean_rent(rent):
    try:
        if pd.isna(rent):
            return np.nan
        cleaned = str(rent).replace('RM ', '').replace(' per month', '').replace(',', '')
        return float(cleaned) if cleaned.strip() else np.nan
    except ValueError:
        return np.nan


def clean_size(size):
    try:
        if pd.isna(size):
            return np.nan
        cleaned = str(size).replace(' sq.ft.', '').replace(',', '')
        return float(cleaned) if cleaned.strip() else np.nan
    except ValueError:
        return np.nan


def clean_rooms(rooms):
    # Normalize mixed int/float strings ("3" vs "3.0") to a canonical int
    # string. Non-numeric labels (e.g. "More than 10") pass through unchanged.
    try:
        if pd.isna(rooms):
            return np.nan
        s = str(rooms).strip()
        if not s:
            return np.nan
        return str(int(float(s)))
    except (ValueError, TypeError):
        return str(rooms).strip()


def clean_rental_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = df.dropna(how='all')

    if 'monthly_rent' in df.columns:
        df['monthly_rent'] = df['monthly_rent'].apply(clean_rent)

    if 'category_id' in df.columns:
        df['category_id'] = df['category_id'].fillna('').astype(str).str.replace(', For rent', '', regex=False)

    if 'size' in df.columns:
        df['size'] = df['size'].apply(clean_size)

    if 'rooms' in df.columns:
        df['rooms'] = df['rooms'].apply(clean_rooms)

    if 'publishedDatetime' in df.columns:
        df['publishedDatetime'] = pd.to_datetime(
            df['publishedDatetime'], errors='coerce', dayfirst=True
        ).dt.strftime(config.DATETIME_FORMAT).fillna('')

    return df


def create_mapping_dict(mapping_df: pd.DataFrame) -> dict:
    mapping_dict = {}
    valid = mapping_df.dropna(subset=["Mudah Property Type", "Standardized Property Type"])
    for _, row in valid.iterrows():
        std_type = str(row["Standardized Property Type"])
        mudah_type = str(row["Mudah Property Type"])
        for t in mudah_type.split("\n"):
            t = t.strip()
            if t:
                mapping_dict[t] = std_type
    return mapping_dict


def clean_raw_files():
    mapping_df = pd.read_csv(config.MAPPING_FILE)
    mapping_dict = create_mapping_dict(mapping_df)

    # Recurse into per-state subdirs (data/raw/<state>/). Skip combined _ALL_
    # snapshots — the per-type files already cover every row, and processing
    # both would double-count. (3_load_to_db upserts by ads_id regardless.)
    raw_files = [
        p for p in config.RAW_DATA_DIR.rglob('*.csv')
        if config.SCRAPED_COMBINED_MARKER not in p.name
    ]
    if not raw_files:
        logger.warning("No raw CSV files found.")
        return

    for raw_path in raw_files:
        out_path = config.PROCESSED_DATA_DIR / raw_path.name
        if out_path.exists():
            logger.info(f"Already processed, skipping: {raw_path.name}")
            continue

        try:
            df = pd.read_csv(raw_path)
            cleaned_df = clean_rental_data(df)

            if 'property_type' in cleaned_df.columns:
                cleaned_df['CPI'] = cleaned_df['property_type'].apply(
                    lambda x: mapping_dict.get(str(x).strip(), 'Other') if pd.notna(x) else 'Other'
                )

            cleaned_df.to_csv(out_path, index=False)
            logger.info(f"Cleaned: {raw_path.name} → {out_path}")

        except Exception as e:
            logger.error(f"Error processing {raw_path.name}: {e}")
            continue


if __name__ == "__main__":
    clean_raw_files()
