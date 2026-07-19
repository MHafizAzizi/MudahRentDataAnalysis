import numpy as np
import pandas as pd
import pytest

from scripts import clean


class TestCleanRent:
    def test_standard_format(self):
        assert clean.clean_rent("RM 1,200 per month") == 1200.0

    def test_large_value(self):
        assert clean.clean_rent("RM 2,500 per month") == 2500.0

    def test_no_comma(self):
        assert clean.clean_rent("RM 800 per month") == 800.0

    def test_none_returns_nan(self):
        assert np.isnan(clean.clean_rent(None))

    def test_invalid_returns_nan(self):
        assert np.isnan(clean.clean_rent("invalid"))

    def test_empty_string_returns_nan(self):
        assert np.isnan(clean.clean_rent(""))

    def test_numeric_input(self):
        assert clean.clean_rent(1500.0) == 1500.0

    def test_nan_input(self):
        assert np.isnan(clean.clean_rent(np.nan))


class TestCleanSize:
    def test_standard_format(self):
        assert clean.clean_size("850 sq.ft.") == 850.0

    def test_with_comma(self):
        assert clean.clean_size("1,200 sq.ft.") == 1200.0

    def test_none_returns_nan(self):
        assert np.isnan(clean.clean_size(None))

    def test_invalid_returns_nan(self):
        assert np.isnan(clean.clean_size("unknown"))

    def test_numeric_input(self):
        assert clean.clean_size(900.0) == 900.0


class TestCleanRooms:
    def test_int_string_unchanged(self):
        assert clean.clean_rooms("3") == "3"

    def test_float_string_to_int(self):
        assert clean.clean_rooms("3.0") == "3"

    def test_numeric_input(self):
        assert clean.clean_rooms(4.0) == "4"

    def test_non_numeric_passthrough(self):
        assert clean.clean_rooms("More than 10") == "More than 10"

    def test_none_returns_nan(self):
        assert np.isnan(clean.clean_rooms(None))

    def test_empty_string_returns_nan(self):
        assert np.isnan(clean.clean_rooms(""))


class TestCleanRentalData:
    def test_monthly_rent_cleaned(self, sample_raw_df):
        result = clean.clean_rental_data(sample_raw_df)
        assert result['monthly_rent'].iloc[0] == 1200.0
        assert result['monthly_rent'].iloc[1] == 2500.0

    def test_null_rent_is_nan(self, sample_raw_df):
        result = clean.clean_rental_data(sample_raw_df)
        assert np.isnan(result['monthly_rent'].iloc[2])

    def test_size_cleaned(self, sample_raw_df):
        result = clean.clean_rental_data(sample_raw_df)
        assert result['size'].iloc[0] == 850.0
        assert result['size'].iloc[1] == 1200.0

    def test_category_strips_for_rent(self, sample_raw_df):
        result = clean.clean_rental_data(sample_raw_df)
        assert 'For rent' not in result['category_id'].iloc[0]

    def test_returns_dataframe(self, sample_raw_df):
        result = clean.clean_rental_data(sample_raw_df)
        assert isinstance(result, pd.DataFrame)

    def test_original_not_modified(self, sample_raw_df):
        original_rent = sample_raw_df['monthly_rent'].iloc[0]
        clean.clean_rental_data(sample_raw_df)
        assert sample_raw_df['monthly_rent'].iloc[0] == original_rent


def test_create_mapping_dict_basic():
    mapping_df = pd.DataFrame({
        "Mudah Property Type": ["Apartment", "Condo\nCondominium"],
        "Standardized Property Type": ["Apartment", "Condominium"],
    })
    result = clean.create_mapping_dict(mapping_df)
    assert result["Apartment"] == "Apartment"
    assert result["Condo"] == "Condominium"
    assert result["Condominium"] == "Condominium"


def test_create_mapping_dict_skips_nan():
    mapping_df = pd.DataFrame({
        "Mudah Property Type": [float("nan"), "House"],
        "Standardized Property Type": ["Should be skipped", "Terrace"],
    })
    result = clean.create_mapping_dict(mapping_df)
    assert "Should be skipped" not in result.values()
    assert result["House"] == "Terrace"
