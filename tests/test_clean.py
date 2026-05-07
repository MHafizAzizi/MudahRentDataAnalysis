import numpy as np
import pandas as pd
import pytest


class TestCleanRent:
    def test_standard_format(self, clean_module):
        assert clean_module.clean_rent("RM 1,200 per month") == 1200.0

    def test_large_value(self, clean_module):
        assert clean_module.clean_rent("RM 2,500 per month") == 2500.0

    def test_no_comma(self, clean_module):
        assert clean_module.clean_rent("RM 800 per month") == 800.0

    def test_none_returns_nan(self, clean_module):
        assert np.isnan(clean_module.clean_rent(None))

    def test_invalid_returns_nan(self, clean_module):
        assert np.isnan(clean_module.clean_rent("invalid"))

    def test_empty_string_returns_nan(self, clean_module):
        assert np.isnan(clean_module.clean_rent(""))

    def test_numeric_input(self, clean_module):
        assert clean_module.clean_rent(1500.0) == 1500.0

    def test_nan_input(self, clean_module):
        assert np.isnan(clean_module.clean_rent(np.nan))


class TestCleanSize:
    def test_standard_format(self, clean_module):
        assert clean_module.clean_size("850 sq.ft.") == 850.0

    def test_with_comma(self, clean_module):
        assert clean_module.clean_size("1,200 sq.ft.") == 1200.0

    def test_none_returns_nan(self, clean_module):
        assert np.isnan(clean_module.clean_size(None))

    def test_invalid_returns_nan(self, clean_module):
        assert np.isnan(clean_module.clean_size("unknown"))

    def test_numeric_input(self, clean_module):
        assert clean_module.clean_size(900.0) == 900.0


class TestCleanRentalData:
    def test_monthly_rent_cleaned(self, clean_module, sample_raw_df):
        result = clean_module.clean_rental_data(sample_raw_df)
        assert result['monthly_rent'].iloc[0] == 1200.0
        assert result['monthly_rent'].iloc[1] == 2500.0

    def test_null_rent_is_nan(self, clean_module, sample_raw_df):
        result = clean_module.clean_rental_data(sample_raw_df)
        assert np.isnan(result['monthly_rent'].iloc[2])

    def test_size_cleaned(self, clean_module, sample_raw_df):
        result = clean_module.clean_rental_data(sample_raw_df)
        assert result['size'].iloc[0] == 850.0
        assert result['size'].iloc[1] == 1200.0

    def test_category_strips_for_rent(self, clean_module, sample_raw_df):
        result = clean_module.clean_rental_data(sample_raw_df)
        assert 'For rent' not in result['category_id'].iloc[0]

    def test_returns_dataframe(self, clean_module, sample_raw_df):
        result = clean_module.clean_rental_data(sample_raw_df)
        assert isinstance(result, pd.DataFrame)

    def test_original_not_modified(self, clean_module, sample_raw_df):
        original_rent = sample_raw_df['monthly_rent'].iloc[0]
        clean_module.clean_rental_data(sample_raw_df)
        assert sample_raw_df['monthly_rent'].iloc[0] == original_rent


def test_create_mapping_dict_basic(clean_module):
    mapping_df = pd.DataFrame({
        "Mudah Property Type": ["Apartment", "Condo\nCondominium"],
        "Standardized Property Type": ["Apartment", "Condominium"],
    })
    result = clean_module.create_mapping_dict(mapping_df)
    assert result["Apartment"] == "Apartment"
    assert result["Condo"] == "Condominium"
    assert result["Condominium"] == "Condominium"


def test_create_mapping_dict_skips_nan(clean_module):
    mapping_df = pd.DataFrame({
        "Mudah Property Type": [float("nan"), "House"],
        "Standardized Property Type": ["Should be skipped", "Terrace"],
    })
    result = clean_module.create_mapping_dict(mapping_df)
    assert "Should be skipped" not in result.values()
    assert result["House"] == "Terrace"
