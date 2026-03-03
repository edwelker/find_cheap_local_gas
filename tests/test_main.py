import pytest
import re
import os
import sys
import importlib
import pandas as pd
from parsel import Selector
import gas_scraper.main as gas
import gas_scraper.config as config
from gas_scraper.parser import clean_address, get_state_hint
from gas_scraper.models import GasStation, GeocodeCache

# --- CLI UI HELPERS TESTS ---


def test_display_region_menu(capsys):
    gas.display_region_menu()
    captured = capsys.readouterr()
    assert "SELECT REGION" in captured.out
    assert "Maryland" in captured.out
    assert "CUSTOM SEARCH" in captured.out


def test_get_user_choice(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *args: "1")
    assert gas.get_user_choice() == "1"


def test_get_user_zip(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *args: "20723")
    assert gas.get_user_zip() == "20723"


def test_wait_for_user_to_confirm_prices(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda *args: "")
    gas.wait_for_user_to_confirm_prices("20723")
    captured = capsys.readouterr()
    assert "ACTION REQUIRED for 20723" in captured.out


# --- ZIP RADIUS TESTS ---


def test_calculate_radius_zips(mocker, monkeypatch):
    monkeypatch.setattr("gas_scraper.main.HAS_RADIUS_LIB", True)
    mock_search_engine = mocker.patch("gas_scraper.main.SearchEngine")
    mock_engine_instance = mock_search_engine.return_value

    # Mock results
    res1 = mocker.MagicMock()
    res1.zipcode = "20723"
    res1.population = 1000
    res1.major_city = "Scaggsville"

    res2 = mocker.MagicMock()
    res2.zipcode = "21044"
    res2.population = 2000
    res2.major_city = "Columbia"

    mock_engine_instance.by_zipcode.return_value.radius.return_value = [res1, res2]

    zips = gas.calculate_radius_zips("20723", miles=15)
    assert "20723" in zips
    assert "21044" in zips
    assert len(zips) == 2


def test_calculate_radius_zips_no_lib(monkeypatch):
    monkeypatch.setattr("gas_scraper.main.HAS_RADIUS_LIB", False)
    # This should print a warning and return just the center zip
    zips = gas.calculate_radius_zips("20723")
    assert zips == ["20723"]


def test_calculate_radius_zips_no_results(mocker, monkeypatch):
    monkeypatch.setattr("gas_scraper.main.HAS_RADIUS_LIB", True)
    mock_search_engine = mocker.patch("gas_scraper.main.SearchEngine")
    mock_engine_instance = mock_search_engine.return_value
    mock_engine_instance.by_zipcode.return_value.radius.return_value = []

    zips = gas.calculate_radius_zips("20723")
    assert zips == ["20723"]


# --- REGION CHOICE TESTS ---


def test_get_region_choice_cli():
    # Test valid choice
    res = gas.get_region_choice(cli_choice="1")
    assert res["name"] == config.REGION_DATA["1"]["name"]
    assert set(res["zips"]) == set(config.REGION_DATA["1"]["zips"].keys())

    # Test invalid choice defaults to "1"
    res = gas.get_region_choice(cli_choice="99")
    assert res["name"] == config.REGION_DATA["1"]["name"]


def test_get_region_choice_custom(monkeypatch):
    monkeypatch.setattr(
        "gas_scraper.main.calculate_radius_zips",
        lambda center, miles=15: ["20723", "21044"],
    )
    res = gas.get_region_choice(cli_choice="4", cli_zip="20723")
    assert res["name"] == "Custom_Radius_20723"
    assert res["zips"] == ["20723", "21044"]


def test_get_region_choice_interactive(monkeypatch):
    monkeypatch.setattr("gas_scraper.main.get_user_choice", lambda: "2")
    res = gas.get_region_choice()
    assert res["name"] == config.REGION_DATA["2"]["name"]


def test_get_region_choice_custom_interactive(monkeypatch):
    monkeypatch.setattr("gas_scraper.main.get_user_choice", lambda: "4")
    monkeypatch.setattr("gas_scraper.main.get_user_zip", lambda: "20723")
    monkeypatch.setattr(
        "gas_scraper.main.calculate_radius_zips", lambda center, miles=15: ["20723"]
    )
    res = gas.get_region_choice()
    assert res["name"] == "Custom_Radius_20723"


# --- SCRAPER TESTS ---


def test_scrape_gasbuddy_comprehensive(mocker):
    mock_wait = mocker.patch("gas_scraper.main.wait_for_user_to_confirm_prices")
    mock_get_cards = mocker.patch("gas_scraper.main.get_station_cards")
    mock_nominatim = mocker.patch("gas_scraper.main.Nominatim")
    mock_init_driver = mocker.patch("gas_scraper.main.init_driver")
    
    # PERFORMANCE: Mock WebDriverWait to avoid 20s timeouts
    mocker.patch("gas_scraper.main.WebDriverWait")
    mocker.patch("gas_scraper.main.EC")

    mock_driver = mocker.MagicMock()
    mock_init_driver.return_value = mock_driver
    mock_driver.page_source = "<html></html>"
    mock_driver.title = "GasBuddy"

    mock_geolocator = mocker.MagicMock()
    mock_nominatim.return_value = mock_geolocator

    def create_card_sel(html):
        return Selector(text=html).xpath("//div")[0]

    # 1. Normal Station (Royal Farms)
    c1 = create_card_sel(
        "<div><h3>Royal Farms</h3><span>123 Main St</span><span>$ 3.50</span></div>"
    )

    # 2. Blocklisted Station (Costco)
    c2 = create_card_sel(
        "<div><h3>Costco</h3><span>456 Oak Ave</span><span>$ 3.30</span></div>"
    )

    # 3. PriceTrends Card (Should be ignored by parser logic if class is present, or by selector)
    # Our new get_station_cards selector already filters PriceTrends, but let's test parser robustness too.
    c3 = create_card_sel(
        '<div class="PriceTrends"><h3>Trends</h3><span>$ 3.40</span></div>'
    )

    # 4. Unknown Address Geocoding Fallback
    c4 = create_card_sel(
        "<div><h3>Mystery Station</h3><span>No Address Here</span><span>$ 3.60</span></div>"
    )

    # 5. Invalid/No Price
    c5 = create_card_sel("<div><h3>No Price Station</h3><span>123 Main St</span></div>")

    # 6. Station name with miles (should be cleaned)
    c6 = create_card_sel(
        "<div><h3>Shell 1.2 mi</h3><span>789 Pine Pike</span><span>$ 3.80</span></div>"
    )

    mock_get_cards.return_value = [c1, c2, c3, c4, c5, c6]

    # Mock Geocoding
    def mock_geocode(query):
        if isinstance(query, dict) and query.get("street") == "123 Main St":
            m = mocker.MagicMock()
            m.latitude = 40.0
            m.longitude = -75.0
            return m
        return None  # Fallback for others

    mock_geolocator.geocode.side_effect = mock_geocode

    region_config = {"name": "Test", "zips": ["20723"]}

    # Test with interactive mode (headless=False)
    mocker.patch("time.sleep")
    data = gas.scrape_gasbuddy(region_config, headless=False)

    assert mock_wait.called
    # Costco filtered (blocklist), c3 might be filtered by get_station_cards or parser
    # c5 filtered (no price)
    # Expected: Royal Farms, Mystery Station, Shell
    stations = [d.station_name for d in data]
    assert "Royal Farms" in stations
    assert "Mystery Station" in stations
    assert "Shell" in stations
    assert len(data) == 3


def test_scrape_gasbuddy_geocoding_error(mocker):
    mocker.patch("gas_scraper.main.load_geo_cache", return_value=GeocodeCache(root={}))
    mock_driver = mocker.MagicMock()
    mocker.patch("gas_scraper.main.init_driver", return_value=mock_driver)
    
    # PERFORMANCE: Mock WebDriverWait to avoid 20s timeouts
    mocker.patch("gas_scraper.main.WebDriverWait")
    mocker.patch("gas_scraper.main.EC")

    mock_driver.page_source = "<html></html>"
    mock_driver.title = "GasBuddy"

    mock_get_cards = mocker.patch("gas_scraper.main.get_station_cards")
    c1 = Selector(
        text="<div><h3>Shell</h3><span>123 Main St</span><span>$ 3.50</span></div>"
    ).xpath("//div")[0]
    mock_get_cards.return_value = [c1]

    mock_nom = mocker.patch("gas_scraper.main.Nominatim")
    mock_geo = mocker.MagicMock()
    mock_nom.return_value = mock_geo
    mock_geo.geocode.side_effect = Exception("Service Down")

    mocker.patch("time.sleep")
    data = gas.scrape_gasbuddy({"name": "T", "zips": ["20723"]}, headless=True)
    assert len(data) == 1
    assert data[0].lat is None


def test_scrape_gasbuddy_parsing_error(mocker):
    mocker.patch("gas_scraper.main.load_geo_cache", return_value=GeocodeCache(root={}))
    mock_driver = mocker.MagicMock()
    mocker.patch("gas_scraper.main.init_driver", return_value=mock_driver)
    
    # PERFORMANCE: Mock WebDriverWait to avoid 20s timeouts
    mocker.patch("gas_scraper.main.WebDriverWait")
    mocker.patch("gas_scraper.main.EC")

    mock_driver.page_source = "<html></html>"
    mock_driver.title = "GasBuddy"

    mock_get_cards = mocker.patch("gas_scraper.main.get_station_cards")
    # Mock a selector that will cause an exception when processed
    mock_sel = mocker.MagicMock(spec=Selector)
    mock_sel.css.side_effect = Exception("Parsing error")
    mock_get_cards.return_value = [mock_sel]

    mocker.patch("time.sleep")
    data = gas.scrape_gasbuddy({"name": "T", "zips": ["20723"]}, headless=True)
    assert len(data) == 0


from click.testing import CliRunner


def test_scrape_gasbuddy_fault_tolerance(mocker):
    """
    Ensures that if one zip code fails (e.g. timeout), others can still succeed.
    """
    mocker.patch("time.sleep")
    mock_init_driver = mocker.patch("gas_scraper.main.init_driver")
    mock_get_cards = mocker.patch("gas_scraper.main.get_station_cards")
    mock_nominatim = mocker.patch("gas_scraper.main.Nominatim")
    
    # PERFORMANCE: Mock WebDriverWait to avoid 20s timeouts
    mocker.patch("gas_scraper.main.WebDriverWait")
    mocker.patch("gas_scraper.main.EC")

    mock_driver = mocker.MagicMock()
    mock_init_driver.return_value = mock_driver
    mock_driver.page_source = "<html></html>"
    mock_driver.title = "GasBuddy"

    # Simulate first zip success, second zip failure (Timeout)
    def side_effect(url):
        if "21044" in url:
            raise Exception("Timeout")
        return None

    mock_driver.get.side_effect = side_effect

    # Mock cards to return something for the successful zip
    mock_get_cards.return_value = ["dummy_card"]

    # Mock parser to return data
    mock_parse = mocker.patch("gas_scraper.main.parse_station_card")
    mock_parse.return_value = GasStation(
        Station="S1",
        Address="A1",
        Zip="20723",
        City="C1",
        Base=3.50,
        discount_amount=0.0,
        Street="A1",
    )

    region_config = {"name": "T", "zips": ["20723", "21044"]}
    data = gas.scrape_gasbuddy(region_config, headless=True)

    # Should have data from one zip, even though the other failed
    assert len(data) == 1
    assert data[0].station_name == "S1"


# --- MAIN TESTS ---


def test_main_success(mocker):
    mock_scrape = mocker.patch("gas_scraper.main.scrape_gasbuddy")
    mocker.patch("os.makedirs")
    mocker.patch("os.path.exists", return_value=True)
    mock_to_csv = mocker.patch("pandas.DataFrame.to_csv")

    mock_scrape.return_value = [
        GasStation(
            City="Scaggsville",
            Zip="20723",
            Station="Royal Farms",
            Address="123 Main St, 20723",
            Base=3.50,
            Discount="Royal Farms",
            discount_amount=0.10,
            Lat=40.0,
            Long=-75.0,
        )
    ]

    runner = CliRunner()
    result = runner.invoke(gas.main, ["1", "--headless"])

    assert result.exit_code == 0
    assert "✅ DATA COLLECTED" in result.output
    assert mock_to_csv.called


def test_main_no_data(mocker):
    mock_scrape = mocker.patch("gas_scraper.main.scrape_gasbuddy", return_value=[])

    runner = CliRunner()
    result = runner.invoke(gas.main, ["1", "--headless"])

    assert result.exit_code == 0
    assert "❌ No data found." in result.output


def test_main_help():
    runner = CliRunner()
    result = runner.invoke(gas.main, ["--help"])
    assert result.exit_code == 0
    assert "Show this message and exit." in result.output


def test_display_results(capsys):
    df = pd.DataFrame(
        [
            {
                "Station": "Test",
                "Net": 3.0,
                "Base": 3.1,
                "Discount": "-",
                "Address": "Addr",
                "City": "City",
            }
        ]
    )
    gas.display_results(df)
    captured = capsys.readouterr()
    assert "📍 VIEW 1: GROUPED BY CITY" in captured.out
    assert "🏆 VIEW 2: CHEAPEST OVERALL" in captured.out


def test_main_single_zip(mocker):
    mock_scrape = mocker.patch("gas_scraper.main.scrape_gasbuddy")
    mock_to_csv = mocker.patch("pandas.DataFrame.to_csv")
    mocker.patch("os.path.exists", return_value=True)
    mocker.patch("os.makedirs")

    # Mock data so that df processing continues
    mock_scrape.return_value = [
        GasStation(
            Station="S1",
            Address="A1",
            City="C1",
            Zip="20723",
            Base=3.1,
            discount_amount=0.1,
            Discount="D1",
        )
    ]

    runner = CliRunner()
    result = runner.invoke(gas.main, ["--zip", "20723", "--headless"])

    assert result.exit_code == 0
    # Verify that scrape_gasbuddy was called correctly
    args, kwargs = mock_scrape.call_args
    assert args[0]["zips"] == ["20723"]

    # Should only be called ONCE (for the latest pointer), NOT for history
    assert mock_to_csv.call_count == 1
    # Check the filename of the single call
    csv_args, _ = mock_to_csv.call_args
    assert "latest_Single_Zip_20723.csv" in csv_args[0]


# --- IMPORT TESTS (TRICKY) ---


def test_import_no_uszipcode(monkeypatch):
    monkeypatch.setitem(sys.modules, "uszipcode", None)
    # Reloading gas with uszipcode missing
    importlib.reload(gas)
    assert gas.HAS_RADIUS_LIB is False
    # Restore gas for other tests
    importlib.reload(gas)
