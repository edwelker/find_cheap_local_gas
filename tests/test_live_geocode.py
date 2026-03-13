import uuid
import pytest
from geopy.geocoders import Nominatim
from gas_scraper.geocode import _perform_geocode
from gas_scraper.models import GeocodeCache

@pytest.mark.live
def test_live_geocode_problematic_address():
    """
    REAL INTEGRATION TEST for geocoding a known problematic address.
    This test makes a live call to the Nominatim API.
    Run this with: pytest -m live
    """
    # Arrange
    geolocator = Nominatim(user_agent="find-cheap-local-gas-scraper-v1-" + str(uuid.uuid4()), timeout=10)
    empty_cache = GeocodeCache(root={})
    
    # This address is known to work on Nominatim if formatted cleanly
    problematic_address = "6425 Dobbin Center Way, 21045"
    cache_key = problematic_address

    # Act & Assert
    # This test is expected to FAIL with a TypeError before the fix is applied.
    # After the fix, it should pass and return a valid coordinate object.
    result = _perform_geocode(
        "Problem Station",
        problematic_address,
        geolocator,
        empty_cache,
        cache_key,
    )
    
    # This assertion will only be reached after the fix is applied.
    assert result is not None
    assert isinstance(result.lat, float)
    assert isinstance(result.lon, float)
    assert 39.0 < result.lat < 40.0
    assert -77.0 < result.lon < -76.0
