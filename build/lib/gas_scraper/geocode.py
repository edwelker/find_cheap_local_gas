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

def is_within_state_bounds(lat: float, lon: float, zip_code: Optional[str]) -> bool:
    """Validates that coordinates fall roughly within expected state boundaries."""
    if not zip_code or len(zip_code) < 2:
        return True
    # MD / DC
    if zip_code.startswith(("20", "21")):
        return 37.5 <= lat <= 40.0 and -80.0 <= lon <= -74.5
    # NY (Long Island / NYC area)
    if zip_code.startswith("11"):
        return 40.4 <= lat <= 41.5 and -74.5 <= lon <= -71.5
    # MA
    if zip_code.startswith("01"):
        return 41.0 <= lat <= 43.0 and -74.0 <= lon <= -69.5
    return True


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
                zip_code=s.zip_code,
            )
            if coords:
                s.lat, s.long = coords.lat, coords.lon
    return stations


def _perform_geocode(
    name, full_address_string, geolocator, geo_cache: GeocodeCache, cache_key, zip_code: Optional[str] = None
) -> Optional[Coordinates]:
    """Helper for Nominatim API with rate limiting, returns Coordinates model."""
    try:
        time.sleep(1.1)

        query = full_address_string
        state_hint = get_state_hint(zip_code) if zip_code else None
        if state_hint and state_hint.lower() not in query.lower():
            query = f"{query}, {state_hint}"

        # Primary geocoding attempt using the cleaned address string and US bias
        location = geolocator.geocode(query, country_codes='us')

        if location:
            if not is_within_state_bounds(location.latitude, location.longitude, zip_code):
                logger.warning(
                    f"⚠️  Coordinates ({location.latitude}, {location.longitude}) out of bounds for {zip_code} ({state_hint}). Rejecting."
                )
                return None

            coords = Coordinates(lat=location.latitude, lon=location.longitude)
            geo_cache.root[cache_key] = coords
            return coords

        logger.warning(f"Geocoding returned None for query: '{query}'")
        return None

    except Exception as e:
        logger.error(f"   ⚠️ Geocoding error for '{cache_key}': {e}")
        return None