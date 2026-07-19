import sys
from pathlib import Path
import pandas as pd
import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def sample_raw_df():
    """Sample raw DataFrame as it comes from the scraper."""
    return pd.DataFrame({
        'ads_id': ['111', '222', '333', '444'],
        'monthly_rent': ['RM 1,200 per month', 'RM 2,500 per month', None, 'invalid'],
        'size': ['850 sq.ft.', '1,200 sq.ft.', None, 'unknown'],
        'category_id': ['Apartment / Condominium, For rent', 'Condominium, For rent', None, ''],
        'property_type': ['Apartment', 'Condominium', 'Others', None],
        'publishedDatetime': ['2025-01-01 10:00', '2025-02-15 12:30', None, 'bad-date'],
        'state': ['Selangor', 'Kuala Lumpur', None, 'Penang'],
    })


@pytest.fixture
def sample_mapping_dict():
    return {
        'Apartment': 'Apartment',
        'Condominium': 'Condominium',
        'Service Residence': 'Condominium',
        '2-storey Terraced House': 'Terraced House',
    }
