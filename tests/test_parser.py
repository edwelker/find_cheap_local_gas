import pytest
from bs4 import BeautifulSoup
from gas_scraper.parser import (
    clean_address, 
    get_state_hint, 
    parse_station_card, 
    geocode_stations,
    extract_base_price,
    clean_station_name,
    get_discount_info,
    is_blocked,
    find_station_card
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


def test_find_station_card():
    html = """
    <div class="StationCard">
        <h3>Station Name</h3>
        <div><span>$ 3.50</span></div>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    price_node = soup.find(string="$ 3.50")
    card = find_station_card(price_node)
    assert card is not None
    assert card.find("h3").text == "Station Name"


# --- EXISTING TESTS (UPDATED FOR MODELS) ---

def test_clean_address():
    assert clean_address("123 Main St\nRegular") == "123 Main St"
    assert clean_address("789 Pine Pke") == "789 Pine Pike"


def test_get_state_hint():
    assert get_state_hint("20723") == "Maryland"


def test_parse_station_card_dependency_injection():
    html = """
    <div>
        <h3>My Custom Station</h3>
        <span>123 Main St</span>
        <span>$ 3.50</span>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    price_node = soup.find(string="$ 3.50")
    
    custom_discounts = {"Custom": 0.50}
    
    data = parse_station_card(
        price_node, "20723", "Scaggsville", 
        discounts=custom_discounts
    )
    
    assert isinstance(data, GasStation)
    assert data.station_name == "My Custom Station"
    assert data.discount_rule == "Custom"
    assert data.net_price == 3.00


def test_geocode_stations(mocker):
    s1 = GasStation(
        City="C1", Zip="20723", Station="S1", 
        Address="123 Main St, 20723", Base=3.50, Street="123 Main St"
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
