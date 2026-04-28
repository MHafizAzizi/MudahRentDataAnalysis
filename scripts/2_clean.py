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


def clean_rental_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = df.dropna(how='all')

    if 'monthly_rent' in df.columns:
        df['monthly_rent'] = df['monthly_rent'].apply(clean_rent)

    if 'category_id' in df.columns:
        df['category_id'] = df['category_id'].fillna('').astype(str).str.replace(', For rent', '', regex=False)

    if 'size' in df.columns:
        df['size'] = df['size'].apply(clean_size)

    if 'publishedDatetime' in df.columns:
        df['publishedDatetime'] = pd.to_datetime(
            df['publishedDatetime'], errors='coerce', dayfirst=True
        ).dt.strftime(config.DATETIME_FORMAT).fillna('')

    return df


def create_mapping_dict(mapping_df: pd.DataFrame) -> dict:
    mapping_dict = {}
    for _, row in mapping_df.iterrows():
        mudah_type = row['Mudah Property Type']
        if pd.isna(mudah_type):
            continue
        std_type = row['Standardized Property Type']
        if pd.isna(std_type) or not str(std_type).startswith('Sewa '):
            continue
        mapped = str(std_type)[5:]
        if '\n' in str(mudah_type):
            for t in str(mudah_type).split('\n'):
                if t.strip():
                    mapping_dict[t.strip()] = mapped
        else:
            mapping_dict[str(mudah_type)] = mapped
    return mapping_dict


def clean_raw_files():
    mapping_df = pd.read_csv(config.MAPPING_FILE)
    mapping_dict = create_mapping_dict(mapping_df)

    raw_files = list(config.RAW_DATA_DIR.glob('*.csv'))
    if not raw_files:
        logger.warning("No raw CSV files found.")
        return

    for raw_path in raw_files:
        try:
            df = pd.read_csv(raw_path)
            cleaned_df = clean_rental_data(df)

            if 'property_type' in cleaned_df.columns:
                cleaned_df['CPI'] = cleaned_df['property_type'].apply(
                    lambda x: mapping_dict.get(str(x).strip(), 'Other') if pd.notna(x) else 'Other'
                )

            out_path = config.PROCESSED_DATA_DIR / raw_path.name
            cleaned_df.to_csv(out_path, index=False)
            logger.info(f"Cleaned: {raw_path.name} → {out_path}")

        except Exception as e:
            logger.error(f"Error processing {raw_path.name}: {e}")
            continue


if __name__ == "__main__":
    clean_raw_files()
