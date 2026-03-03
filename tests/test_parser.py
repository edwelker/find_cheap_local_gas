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


def test_get_station_cards():
    html = """
    <html>
        <body>
            <div class="StationCard">
                <h3>Station 1</h3>
                <span>$ 3.50</span>
            </div>
            <div class="PriceTrends">
                <h3>Trends</h3>
                <span>$ 3.40</span>
            </div>
            <div class="AnotherCard">
                <h3>Station 2</h3>
                <span>$ 3.60</span>
            </div>
        </body>
    </html>
    """
    cards = get_station_cards(html)
    assert len(cards) == 2
    assert cards[0].css("h3::text").get() == "Station 1"
    assert cards[1].css("h3::text").get() == "Station 2"


# --- EXISTING TESTS (UPDATED FOR MODELS & PARSEL) ---


def test_clean_address():
    assert clean_address("123 Main St\nRegular") == "123 Main St"
    assert clean_address("789 Pine Pke") == "789 Pine Pike"


def test_get_state_hint():
    assert get_state_hint("20723") == "Maryland"


def test_parse_station_card_dependency_injection():
    html = """
    <div class="Container">
        <h3>My Custom Station</h3>
        <span>123 Main St</span>
        <span>$ 3.50</span>
    </div>
    """
    sel = Selector(text=html).css("h3")[0]

    custom_discounts = {"Custom": 0.50}

    data = parse_station_card(
        sel, "20723", "Scaggsville", 
        discounts=custom_discounts
    )


    assert isinstance(data, GasStation)
    assert data.station_name == "My Custom Station"
    assert data.discount_rule == "Custom"
    assert data.net_price == 3.00


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
