import pytest
from bs4 import BeautifulSoup
from unittest.mock import MagicMock, patch
from gas_scraper.parser import clean_address, get_state_hint, parse_station_card

def test_clean_address():
    assert clean_address("123 Main St\nRegular") == "123 Main St"
    assert clean_address("789 Pine Pke") == "789 Pine Pike"
    assert clean_address("Unknown") == "Unknown Address"

def test_get_state_hint():
    assert get_state_hint("20723") == "Maryland"
    assert get_state_hint("11901") == "New York"
    assert get_state_hint("90210") is None

def test_parse_station_card_valid():
    html = """
    <div class="StationCard">
        <h3>Royal Farms</h3>
        <span>123 Main St</span>
        <div class="Price">
            <span>$ 3.50</span>
        </div>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    price_node = soup.find(string="$ 3.50")
    
    geolocator = MagicMock()
    mock_loc = MagicMock()
    mock_loc.latitude = 40.0
    mock_loc.longitude = -75.0
    geolocator.geocode.return_value = mock_loc
    
    geo_cache = {}
    
    with patch("time.sleep"): # Skip sleep in tests
        data = parse_station_card(price_node, "20723", "Scaggsville", geolocator, geo_cache)
    
    assert data["Station"] == "Royal Farms"
    assert data["Base"] == 3.50
    assert data["Net"] == 3.40 # 3.50 - 0.10 discount
    assert data["Lat"] == 40.0
    assert "123 Main St, 20723" in geo_cache

def test_parse_station_card_blocklisted():
    html = """
    <div>
        <h3>Costco</h3>
        <span>456 Oak Ave</span>
        <span>$ 3.30</span>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    price_node = soup.find(string="$ 3.30")
    
    data = parse_station_card(price_node, "20723", "Scaggsville", MagicMock(), {})
    assert data is None

def test_parse_station_card_trend():
    html = """
    <div class="PriceTrendsContainer">
        <span>$ 3.40</span>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    price_node = soup.find(string="$ 3.40")
    
    data = parse_station_card(price_node, "20723", "Scaggsville", MagicMock(), {})
    assert data is None
