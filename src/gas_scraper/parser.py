import re
import time
from .config import BLOCKLIST, DISCOUNTS

def clean_address(full_text):
    """
    Parses a blob of text to find the street address line.
    Filters out 'Cash/Credit' and fuel grades.
    """
    # Fix for "Pke" abbreviation -> "Pike"
    full_text = re.sub(r"\bPke\b", "Pike", full_text, flags=re.IGNORECASE)

    lines = re.split(r"\s{2,}|\n", full_text)
    bad_keywords = [
        "Regular", "Premium", "Diesel", "Midgrade", "UNL88",
        "Cash", "Credit", "Station Brand", "Payment", "Hours", "ago",
    ]

    # Regex: Starts with digits, followed by words.
    addr_regex = re.compile(
        r"^\d{1,5}\s+[A-Za-z0-9\.\s\-\,']+",
        re.IGNORECASE,
    )

    for line in lines:
        line = line.strip()
        if any(bad in line for bad in bad_keywords):
            continue

        match = addr_regex.search(line)
        if match:
            return match.group(0).strip()

    return "Unknown Address"


def get_state_hint(zip_code):
    """
    Returns a state name based on the zip code prefix to help the geocoder.
    """
    if zip_code.startswith(("20", "21")):
        return "Maryland"
    if zip_code.startswith("11"):
        return "New York"
    if zip_code.startswith("01"):
        return "Massachusetts"
    return None


def parse_station_card(price_node, zip_code, city_name, geolocator, geo_cache):
    """
    Walks up from a price node to find the station card, extracts details,
    applies business logic, and returns a dictionary of station data.
    """
    try:
        # 1. Parse Base Price
        price_regex = re.compile(r"\$\s*([2-5]\.\d{2})")
        match = price_regex.search(price_node)
        if not match:
            return None
        base_price = float(match.group(1))

        # 2. Walk up to find the "Card"
        card = price_node.parent
        depth = 0
        is_trend = False

        while card and depth < 8:
            # Check if this element indicates a Price Trend panel
            if card.name:
                classes = card.get("class", [])
                if classes and any("PriceTrends" in c for c in classes):
                    is_trend = True
                    break

            if card.name == "div" and card.find("h3"):
                break
            card = card.parent
            depth += 1

        if not card or is_trend:
            return None

        # 3. Extract Name
        name_tag = card.find("h3")
        name = name_tag.get_text(strip=True) if name_tag else "Unknown"
        name = re.sub(r"\d+(\.\d+)?\s*mi.*", "", name).strip()

        # 4. Extract & Clean Address
        full_text = card.get_text("\n", strip=True)
        street_addr = clean_address(full_text)
        full_address = f"{street_addr}, {zip_code}"

        # 5. Filter Blocklist (Checks Name AND Address)
        if any(b.lower() in name.lower() for b in BLOCKLIST):
            return None
        if any(b.lower() in full_address.lower() for b in BLOCKLIST):
            return None

        # 6. Apply Discounts
        discount = 0.0
        rule = "-"
        for brand, amount in DISCOUNTS.items():
            if brand.lower() in name.lower():
                discount = amount
                rule = brand
                break

        # 7. Geocoding logic
        lat, lng = _geocode_station(name, street_addr, zip_code, geolocator, geo_cache)

        return {
            "City": city_name,
            "Zip": zip_code,
            "Station": name,
            "Address": full_address,
            "Base": base_price,
            "Net": round(base_price - discount, 2),
            "Discount": rule,
            "Lat": lat,
            "Long": lng,
        }

    except Exception:
        return None


def _geocode_station(name, street_addr, zip_code, geolocator, geo_cache):
    """
    Helper to handle geocoding with caching and fallback logic.
    """
    # Determine cache key
    if street_addr != "Unknown Address":
        cache_key = f"{street_addr}, {zip_code}"
    else:
        cache_key = f"{name}, {zip_code}"

    if cache_key in geo_cache:
        return geo_cache[cache_key]

    try:
        # Rate limiting for Nominatim (1 sec)
        time.sleep(1.1)

        location = None
        state_hint = get_state_hint(zip_code)

        # 1. Try Structured Query (Most Accurate)
        if street_addr != "Unknown Address":
            query = {
                "street": street_addr,
                "postalcode": zip_code,
                "country": "USA",
            }
            if state_hint:
                query["state"] = state_hint
            location = geolocator.geocode(query)

        # 2. Fallback: Free-form string query
        if not location:
            parts = []
            if street_addr != "Unknown Address":
                parts.append(street_addr)
            else:
                parts.append(name)
            parts.append(zip_code)
            if state_hint:
                parts.append(state_hint)
            parts.append("USA")

            q_str = ", ".join(parts)
            location = geolocator.geocode(q_str)

        if location:
            res = (location.latitude, location.longitude)
        else:
            res = (None, None)

        geo_cache[cache_key] = res
        return res

    except Exception as e:
        print(f"   ⚠️ Geocoding error for '{cache_key}': {e}")
        return (None, None)
