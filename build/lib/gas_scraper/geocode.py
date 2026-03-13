import json
import os
import time
from typing import Optional
from loguru import logger
from .models import GeocodeCache, Coordinates

CACHE_FILE = "geocache.json"

def load_geo_cache() -> GeocodeCache:
    """PERFORMANCE: Load previous geocoding results as a Pydantic model."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                data = json.load(f)
                return GeocodeCache.model_validate(data)
        except Exception as e:
            logger.warning(f"⚠️  Error loading geocache: {e}")
    return GeocodeCache(root={})

def save_geo_cache(cache: GeocodeCache):
    """PERFORMANCE: Save results to disk using Pydantic serialization."""
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache.model_dump(), f, indent=2)
    except Exception as e:
        logger.error(f"⚠️  Error saving geocache: {e}")

def get_state_hint(zip_code):
    """Returns state name based on zip code prefix."""
    if zip_code.startswith(("20", "21")):
        return "Maryland"
    if zip_code.startswith("11"):
        return "New York"
    if zip_code.startswith("01"):
        return "Massachusetts"
    return None

def geocode_stations(stations, geolocator, geo_cache: GeocodeCache):
    """Batch geocodes GasStation objects using the structured cache model."""
    logger.info(f"🌍 Geocoding {len(stations)} unique stations...")
    for s in stations:
        cache_key = (
            f"{s.street_name}, {s.zip_code}"
            if s.street_name != "Unknown Address"
            else f"{s.station_name}, {s.zip_code}"
        )

        if cache_key in geo_cache.root:
            logger.debug(f"   Cache hit for: '{cache_key}'")
            coords = geo_cache.root[cache_key]
            s.lat, s.long = coords.lat, coords.lon
        else:
            logger.info(f"   Geocoding new address: '{cache_key}'")
            coords = _perform_geocode(
                s.station_name,
                s.address, # Use the full address string
                geolocator,
                geo_cache,
                cache_key,
            )
            if coords:
                s.lat, s.long = coords.lat, coords.lon
    return stations

def _perform_geocode(
    name, full_address_string, geolocator, geo_cache: GeocodeCache, cache_key
) -> Optional[Coordinates]:
    """Helper for Nominatim API with rate limiting, returns Coordinates model."""
    try:
        time.sleep(1.1)

        # Primary geocoding attempt using the cleaned address string and US bias
        location = geolocator.geocode(full_address_string, country_codes='us')

        if location:
            coords = Coordinates(lat=location.latitude, lon=location.longitude)
            geo_cache.root[cache_key] = coords
            return coords

        logger.warning(f"Geocoding returned None for query: '{full_address_string}'")
        return None

    except Exception as e:
        logger.error(f"   ⚠️ Geocoding error for '{cache_key}': {e}")
        return None