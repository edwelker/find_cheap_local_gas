import pytest
from parsel import Selector
from gas_scraper.parser import (
    clean_address,
    get_state_hint,
    parse_station_card,
    geocode_stations,
    extract_base_price,
    clean_station_name,
    get_discount_info,
    is_blocked,
    get_station_cards,
)
from gas_scraper.models import GasStation, GeocodeCache, Coordinates

# --- UNIT TESTS FOR PURE FUNCTIONS ---


def test_extract_base_price():
    assert extract_base_price("$ 3.45") == 3.45
    assert extract_base_price("Price: $2.99") == 2.99
    assert extract_base_price("No price here") is None
    assert extract_base_price("$ 6.00") is None


def test_clean_station_name():
    assert clean_station_name("Royal Farms 2.3 mi") == "Royal Farms"
    assert clean_station_name("Shell 0.5 mi away") == "Shell"


def test_get_discount_info():
    discounts = {"Royal Farms": 0.10, "Shell": 0.05}
    amt, rule = get_discount_info("Royal Farms #123", discounts)
    assert amt == 0.10
    assert rule == "Royal Farms"


def test_is_blocked():
    blocklist = ["Costco"]
    assert is_blocked("Costco Wholesale", "Main St", blocklist) is True
    assert is_blocked("Shell", "456 Oak Ave", blocklist) is False


# --- MOCK HTML FIXTURE FOR INTEGRATION TESTS ---

MOCK_HTML = """
<html>
<body>
  <div class="GenericStationListItem-module__station___1O2q_">
    <h3><a href="#">Shell</a></h3>
    <div class="StationDisplay-module__address___1O2q_">123 Main St</div>
    <div class="StationDisplayPrice-module__price___1O2q_"><span>$3.50</span></div>
  </div>
  <div class="GenericStationListItem-module__station___1O2q_">
    <h3><a href="#">Exxon</a></h3>
    <div class="StationDisplay-module__address___1O2q_">456 Oak Ave</div>
    <div class="StationDisplayPrice-module__price___1O2q_"><span>$3.60</span></div>
  </div>
  <div class="GenericStationListItem-module__station___1O2q_">
    <h3><a href="#">Costco</a></h3>
    <div class="StationDisplay-module__address___1O2q_">789 Pine Rd</div>
    <div class="StationDisplayPrice-module__price___1O2q_"><span>$3.40</span></div>
  </div>
</body>
</html>
"""

# --- UNIT TESTS FOR PURE FUNCTIONS ---

def test_extract_base_price():
    assert extract_base_price("$3.45") == 3.45
    assert extract_base_price("Price: $2.99") == 2.99
    assert extract_base_price("No price here") is None
    assert extract_base_price("$6.00") is None


def test_clean_station_name():
    assert clean_station_name("Royal Farms 2.3 mi") == "Royal Farms"
    assert clean_station_name("Shell 0.5 mi away") == "Shell"


def test_get_discount_info():
    discounts = {"Royal Farms": 0.10, "Shell": 0.05}
    amt, rule = get_discount_info("Royal Farms #123", discounts)
    assert amt == 0.10
    assert rule == "Royal Farms"


def test_is_blocked():
    blocklist = ["Costco"]
    assert is_blocked("Costco Wholesale", "Main St", blocklist) is True
    assert is_blocked("Shell", "456 Oak Ave", blocklist) is False


def test_get_station_cards():
    cards = get_station_cards(MOCK_HTML)
    assert len(cards) == 3


# --- INTEGRATION TEST FOR PARSING LOGIC ---

def test_parse_station_card_with_fixture():
    # Use the first card from our mock HTML
    card_sel = get_station_cards(MOCK_HTML)[0]
    
    # Define custom rules for this test
    custom_discounts = {"Shell": 0.10}
    custom_blocklist = ["Costco"]

    # Parse the card
    station = parse_station_card(
        card_sel, 
        "20723", 
        "Scaggsville", 
        discounts=custom_discounts, 
        blocklist=custom_blocklist
    )

    # Assertions
    assert isinstance(station, GasStation)
    assert station.station_name == "Shell"
    assert station.street_name == "123 Main St"
    assert station.base_price == 3.50
    assert station.discount_amount == 0.10
    assert station.net_price == 3.40
    assert station.discount_rule == "Shell"

def test_parse_station_card_blocking():
    # Use the third card (Costco) from our mock HTML
    card_sel = get_station_cards(MOCK_HTML)[2]
    
    # Define a blocklist
    custom_blocklist = ["Costco"]

    # Attempt to parse the blocked station
    station = parse_station_card(
        card_sel, 
        "20723", 
        "Scaggsville", 
        blocklist=custom_blocklist
    )

    # Assert that the station was correctly blocked
    assert station is None


# --- EXISTING TESTS (UPDATED FOR MODELS & PARSEL) ---


def test_clean_address():
    assert clean_address("123 Main St\nRegular") == "123 Main St"
    assert clean_address("789 Pine Pke") == "789 Pine Pike"


def test_get_state_hint():
    assert get_state_hint("20723") == "Maryland"




def test_geocode_stations(mocker):
    s1 = GasStation(
        City="C1",
        Zip="20723",
        Station="S1",
        Address="123 Main St, 20723",
        Base=3.50,
        Street="123 Main St",
    )

    geolocator = mocker.MagicMock()
    mock_loc = mocker.MagicMock()
    mock_loc.latitude = 40.0
    mock_loc.longitude = -75.0
    geolocator.geocode.return_value = mock_loc

    geo_cache = GeocodeCache(root={})
    mocker.patch("time.sleep")

    res = geocode_stations([s1], geolocator, geo_cache)

    assert res[0].lat == 40.0
    assert "123 Main St, 20723" in geo_cache.root
    assert isinstance(geo_cache.root["123 Main St, 20723"], Coordinates)
