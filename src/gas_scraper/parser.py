import re
from typing import List, Optional
from parsel import Selector
from loguru import logger
from .config import BLOCKLIST, DISCOUNTS
from .models import GasStation
from .geocode import load_geo_cache, save_geo_cache, get_state_hint, geocode_stations


def clean_address(full_text):
    """Parses a blob of text to find the street address line."""
    full_text = re.sub(r"\bPke\b", "Pike", full_text, flags=re.IGNORECASE)
    lines = re.split(r"\s{2,}|\n", full_text)
    bad_keywords = [
        "Regular",
        "Premium",
        "Diesel",
        "Midgrade",
        "UNL88",
        "Cash",
        "Credit",
        "Payment",
        "Hours",
        "ago",
    ]
    addr_regex = re.compile(r"^\d{1,5}\s+[A-Za-z0-9\.\s\-\,']+", re.IGNORECASE)

    for line in lines:
        line = line.strip()
        if any(bad in line for bad in bad_keywords):
            continue
        match = addr_regex.search(line)
        if match:
            return match.group(0).strip()
    return "Unknown Address"


def extract_base_price(price_text):
    """Pure function: Extracts float price from string."""
    match = re.search(r"\$\s*([2-5]\.\d{2})", price_text)
    return float(match.group(1)) if match else None


def clean_station_name(raw_name):
    """Pure function: Removes distance markers from station name."""
    return re.sub(r"\d+(\.\d+)?\s*mi.*", "", raw_name).strip()


def get_discount_info(name, discounts):
    """Pure function: Returns (amount, brand)."""
    for brand, amount in discounts.items():
        if brand.lower() in name.lower():
            return float(amount), brand
    return 0.0, "-"


def is_blocked(name, address, blocklist):
    """Pure function: Checks blocklist."""
    n, a = name.lower(), address.lower()
    return any(b.lower() in n or b.lower() in a for b in blocklist)


def get_station_cards(html: str) -> List[Selector]:
    """Finds all station card containers in the page using Parsel."""
    sel = Selector(text=html)
    # Find all potential station containers. The parser will validate them.
    return sel.xpath("//div[starts-with(@class, 'GenericStationListItem-module__station')]")


def parse_station_card(card_sel: Selector, zip_code, city_name, discounts=DISCOUNTS, blocklist=BLOCKLIST) -> Optional[GasStation]:
    """Orchestrates data extraction from a Parsel Selector into a GasStation model."""
    try:
        # Extract name from h3
        name_list = card_sel.xpath(
            ".//h3[contains(@class, 'StationDisplay-module__stationName')]//text()"
        ).getall()
        name_raw = "".join(name_list).strip()
        if not name_raw:
            return None
        name = clean_station_name(name_raw)

        # Extract address from its div
        address_list = card_sel.xpath(
            ".//div[contains(@class, 'StationDisplay-module__address')]//text()"
        ).getall()
        address_raw = "\n".join(address_list).strip()
        if not address_raw:
            return None
        street_addr = clean_address(address_raw)
        full_address = f"{street_addr}, {zip_code}"

        # Extract price from its specific span
        price_list = card_sel.xpath(
            ".//span[contains(@class, 'StationDisplayPrice-module__price')]//text()"
        ).getall()
        price_text = "".join(price_list).strip()
        if not price_text:
            return None
        base_price = extract_base_price(price_text)
        if base_price is None:
            return None

        # Run checks and compute final values
        if is_blocked(name, full_address, blocklist):
            return None

        discount_amount, discount_rule = get_discount_info(name, discounts)

        return GasStation(
            City=city_name,
            Zip=zip_code,
            Station=name,
            Address=full_address,
            Base=base_price,
            Discount=discount_rule,
            discount_amount=discount_amount,
            Street=street_addr,
        )
    except Exception:
        return None