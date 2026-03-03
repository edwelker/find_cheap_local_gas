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
# These are verbatim copies of two station listings from a real GasBuddy page.
MOCK_HTML = """
<body>
    <div class="panel__panel___3Q2zW panel__white___19KTz colors__bgWhite___1stjL panel__bordered___1Xe-S panel__rounded___2etNE GenericStationListItem-module__station___1O4vF" id="75337">
        <div class="GenericStationListItem-module__stationListItem___3Jmn4">
            <div class="StationDisplay-module__mainInfoColumn___1ZBwz StationDisplay-module__column___3h4Wf">
                <h3 class="header__header3___1b1oq header__header___1zII0 header__midnight___1tdCQ header__snug___lRSNK StationDisplay-module__stationNameHeader___1A2q8">
                    <a style="color: inherit; font-weight: 700; text-decoration: inherit" href="/station/75337">7-Eleven</a><span> </span>
                </h3>
                <div class="StationDisplay-module__address___2_c7v">
                    9651 Washington Blvd N<br />Laurel, MD
                </div>
            </div>
            <div class="GenericStationListItem-module__priceCard___27wng">
                <span class="text__xl___2MXGo text__left___1iOw3 StationDisplayPrice-module__price___3rARL">$2.85</span>
            </div>
        </div>
    </div>
    <div class="panel__panel___3Q2zW panel__white___19KTz colors__bgWhite___1stjL panel__bordered___1Xe-S panel__rounded___2etNE GenericStationListItem-module__station___1O4vF" id="122963">
        <div class="GenericStationListItem-module__stationListItem___3Jmn4">
            <div class="StationDisplay-module__mainInfoColumn___1ZBwz StationDisplay-module__column___3h4Wf">
                <h3 class="header__header3___1b1oq header__header___1zII0 header__midnight___1tdCQ header__snug___lRSNK StationDisplay-module__stationNameHeader___1A2q8">
                    <a style="color: inherit; font-weight: 700; text-decoration: inherit" href="/station/122963">Weis</a><span> </span>
                </h3>
                <div class="StationDisplay-module__address___2_c7v">
                    9250 Washington Blvd N<br />Savage, MD
                </div>
            </div>
            <div class="GenericStationListItem-module__priceCard___27wng">
                <span class="text__xl___2MXGo text__left___1iOw3 StationDisplayPrice-module__price___3rARL">$2.85</span>
            </div>
        </div>
    </div>
    <div class="GenericStationListItem-module__station___PHANTOM">
        <p>This phantom div should be ignored by the parser.</p>
    </div>
</body>
"""

# --- UNIT TESTS FOR PURE FUNCTIONS ---

def test_extract_base_price():
    assert extract_base_price("$3.45") == 3.45
    assert extract_base_price("No price here") is None
    assert extract_base_price("$6.00") is None


def test_clean_station_name():
    assert clean_station_name("7-Eleven 1.2 mi") == "7-Eleven"


def test_get_discount_info():
    discounts = {"7-Eleven": 0.10}
    amt, rule = get_discount_info("7-Eleven #123", discounts)
    assert amt == 0.10
    assert rule == "7-Eleven"


def test_is_blocked():
    assert is_blocked("Costco", "123 Main St", ["Costco"]) is True


def test_get_station_cards():
    # Should find 3 potential containers (2 real + 1 phantom)
    cards = get_station_cards(MOCK_HTML)
    assert len(cards) == 3


# --- INTEGRATION TEST FOR PARSING LOGIC ---

def test_parse_station_card_with_fixture():
    # The parser should correctly parse the first (valid) card
    card_sel = get_station_cards(MOCK_HTML)[0]
    station = parse_station_card(card_sel, "20723", "Laurel")
    assert isinstance(station, GasStation)
    assert station.station_name == "7-Eleven"
    assert station.street_name == "9651 Washington Blvd N Laurel, MD"
    assert station.base_price == 2.85

    # The parser should correctly parse the second (valid) card
    card_sel_weis = get_station_cards(MOCK_HTML)[1]
    station_weis = parse_station_card(card_sel_weis, "20723", "Savage")
    assert isinstance(station_weis, GasStation)
    assert station_weis.station_name == "Weis"
    assert station_weis.street_name == "9250 Washington Blvd N Savage, MD"
    assert station_weis.base_price == 2.85

    # The parser should return None for the third (phantom) card
    card_sel_phantom = get_station_cards(MOCK_HTML)[2]
    station_phantom = parse_station_card(card_sel_phantom, "20723", "Laurel")
    assert station_phantom is None


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
