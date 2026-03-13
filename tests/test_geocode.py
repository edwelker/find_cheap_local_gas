import pytest
from unittest.mock import MagicMock, patch
from gas_scraper.geocode import (
    _perform_geocode,
    geocode_stations,
    load_geo_cache,
    save_geo_cache,
    get_state_hint,
)
from gas_scraper.models import GasStation, GeocodeCache, Coordinates


@pytest.fixture
def mock_geolocator():
    """Fixture for a MagicMock of the Nominatim geolocator."""
    return MagicMock()


@pytest.fixture
def empty_geo_cache():
    """Fixture for an empty GeocodeCache."""
    return GeocodeCache(root={})


def test_perform_geocode_success(mock_geolocator, empty_geo_cache):
    """
    Test that _perform_geocode successfully geocodes and caches a valid address.
    """
    # Arrange
    mock_location = MagicMock()
    mock_location.latitude = 39.123
    mock_location.longitude = -76.456
    mock_geolocator.geocode.return_value = mock_location

    cache_key = "123 Main St, 20723"

    # Act
    result = _perform_geocode(
        "Test Station",
        cache_key,
        mock_geolocator,
        empty_geo_cache,
        cache_key,
    )

    # Assert
    assert result is not None
    assert result.lat == 39.123
    assert result.lon == -76.456
    assert cache_key in empty_geo_cache.root
    assert empty_geo_cache.root[cache_key].lat == 39.123


def test_perform_geocode_problematic_address(mock_geolocator, empty_geo_cache):
    """
    Test that _perform_geocode successfully geocodes the previously problematic address.
    """
    # Arrange
    problematic_address = "6425 Dobbin Center Way Columbia, MD, 21045"
    mock_location = MagicMock()
    mock_location.latitude = 39.1995171
    mock_location.longitude = -76.8147101
    mock_geolocator.geocode.return_value = mock_location

    cache_key = problematic_address

    # Act
    result = _perform_geocode(
        "Problem Station",
        problematic_address,
        mock_geolocator,
        empty_geo_cache,
        cache_key,
    )

    # Assert
    assert result is not None
    assert result.lat == 39.1995171
    assert result.lon == -76.8147101
    assert cache_key in empty_geo_cache.root
    assert empty_geo_cache.root[cache_key].lat == 39.1995171


def test_perform_geocode_failure_does_not_cache(mock_geolocator, empty_geo_cache):
    """
    Test that _perform_geocode returns None and does NOT cache when geocoding fails.
    """
    # Arrange
    mock_geolocator.geocode.return_value = None
    cache_key = "Invalid Address, 99999"

    # Act
    result = _perform_geocode(
        "Nowhere Station",
        cache_key,
        mock_geolocator,
        empty_geo_cache,
        cache_key,
    )

    # Assert
    assert result is None
    assert cache_key not in empty_geo_cache.root


def test_geocode_stations_integration(mock_geolocator, empty_geo_cache):
    """
    Test the full geocode_stations flow with a mix of cached, new, and invalid addresses.
    """
    # Arrange
    # 1. Pre-populate the cache with one station
    cached_key = "1 Cached St, 12345"
    empty_geo_cache.root[cached_key] = Coordinates(lat=1.1, lon=2.2)

    # 2. Mock the geolocator for new lookups
    valid_location = MagicMock()
    valid_location.latitude = 3.3
    valid_location.longitude = 4.4
    mock_geolocator.geocode.side_effect = [valid_location, None] # First call succeeds, second fails

    # 3. Create station objects
    stations = [
        GasStation(Station="Cached Station", Street="1 Cached St", Zip="12345", City="Testville", Address="1 Cached St, 12345", Base=1.0, Discount="-"),
        GasStation(Station="New Valid Station", Street="2 New St", Zip="67890", City="Testville", Address="2 New St, 67890", Base=1.0, Discount="-"),
        GasStation(Station="Invalid Station", Street="3 Nowhere St", Zip="00000", City="Testville", Address="3 Nowhere St, 00000", Base=1.0, Discount="-"),
    ]
    # Act
    geocoded_stations = geocode_stations(stations, mock_geolocator, empty_geo_cache)

    # Assert
    # Station 1 (Cached)
    assert geocoded_stations[0].lat == 1.1
    assert geocoded_stations[0].long == 2.2

    # Station 2 (New Valid)
    assert geocoded_stations[1].lat == 3.3
    assert geocoded_stations[1].long == 4.4
    assert "2 New St, 67890" in empty_geo_cache.root
    assert empty_geo_cache.root["2 New St, 67890"].lat == 3.3

    # Station 3 (Invalid)
    assert geocoded_stations[2].lat is None
    assert geocoded_stations[2].long is None
    assert "3 Nowhere St, 00000" not in empty_geo_cache.root


def test_get_state_hint():
    """Test the state hint logic."""
    assert get_state_hint("20723") == "Maryland"
    assert get_state_hint("11901") == "New York"
    assert get_state_hint("01060") == "Massachusetts"
    assert get_state_hint("90210") is None
