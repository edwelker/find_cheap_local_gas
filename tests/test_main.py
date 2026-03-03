import pytest
import re
import os
import sys
import importlib
import pandas as pd
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
    monkeypatch.setattr("gas_scraper.main.calculate_radius_zips", lambda center, miles=15: ["20723", "21044"])
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
    monkeypatch.setattr("gas_scraper.main.calculate_radius_zips", lambda center, miles=15: ["20723"])
    res = gas.get_region_choice()
    assert res["name"] == "Custom_Radius_20723"

# --- SCRAPER TESTS ---

def test_scrape_gasbuddy_comprehensive(mocker):
    mock_wait = mocker.patch("gas_scraper.main.wait_for_user_to_confirm_prices")
    mock_bs = mocker.patch("gas_scraper.main.BeautifulSoup")
    mock_nominatim = mocker.patch("gas_scraper.main.Nominatim")
    mock_init_driver = mocker.patch("gas_scraper.main.init_driver")
    
    mock_driver = mocker.MagicMock()
    mock_init_driver.return_value = mock_driver
    
    mock_geolocator = mocker.MagicMock()
    mock_nominatim.return_value = mock_geolocator
    
    # Mock BeautifulSoup to find prices and cards
    mock_soup = mocker.MagicMock()
    mock_bs.return_value = mock_soup
    
    def create_price_node(price_str):
        node = mocker.MagicMock()
        node.get_text.return_value = price_str
        return node

    # 1. Normal Station (Royal Farms)
    p1 = create_price_node("$ 3.50")
    c1 = mocker.MagicMock()
    c1.name = "div"
    c1.get.return_value = ["SomeClass"]
    c1.find.side_effect = lambda tag, **kwargs: mocker.MagicMock(get_text=lambda strip=True: "Royal Farms") if tag == "h3" else None
    c1.get_text.return_value = "Royal Farms\n123 Main St\n$ 3.50"
    p1.parent = c1

    # 2. Blocklisted Station (Costco)
    p2 = create_price_node("$ 3.30")
    c2 = mocker.MagicMock()
    c2.name = "div"
    c2.get.return_value = ["SomeClass"]
    c2.find.side_effect = lambda tag, **kwargs: mocker.MagicMock(get_text=lambda strip=True: "Costco") if tag == "h3" else None
    c2.get_text.return_value = "Costco\n456 Oak Ave\n$ 3.30"
    p2.parent = c2

    # 3. PriceTrends Card (Should be ignored)
    p3 = create_price_node("$ 3.40")
    c3 = mocker.MagicMock()
    c3.name = "div"
    c3.get.return_value = ["PriceTrendsContainer"]
    c3.find.return_value = None
    c3.get_text.return_value = "Price Trends\n$ 3.40"
    p3.parent = c3

    # 4. Unknown Address Geocoding Fallback
    p4 = create_price_node("$ 3.60")
    c4 = mocker.MagicMock()
    c4.name = "div"
    c4.get.return_value = []
    c4.find.side_effect = lambda tag, **kwargs: mocker.MagicMock(get_text=lambda strip=True: "Mystery Station") if tag == "h3" else None
    c4.get_text.return_value = "Mystery Station\nNo Address Here\n$ 3.60"
    p4.parent = c4
    
    # 5. Card not found (depth limit reached)
    p5 = create_price_node("$ 3.70")
    p5.parent = mocker.MagicMock()
    p5.parent.name = "span"
    p5.parent.get.return_value = []
    p5.parent.find.return_value = None
    # Chain of parents that never find a card with h3
    curr = p5.parent
    for _ in range(10):
        curr.parent = mocker.MagicMock()
        curr.parent.name = "span"
        curr.parent.get.return_value = []
        curr.parent.find.return_value = None
        curr = curr.parent

    # 6. Station name with miles (should be cleaned)
    p6 = create_price_node("$ 3.80")
    c6 = mocker.MagicMock()
    c6.name = "div"
    c6.get.return_value = None # Hits line 358: if classes and any(...)
    c6.find.side_effect = lambda tag, **kwargs: mocker.MagicMock(get_text=lambda strip=True: "Shell 1.2 mi") if tag == "h3" else None
    c6.get_text.return_value = "Shell 1.2 mi\n789 Pine Pike\n$ 3.80"
    p6.parent = c6

    mock_soup.find_all.return_value = [p1, p2, p3, p4, p5, p6]
    
    # Mock Geocoding
    def mock_geocode(query):
        if isinstance(query, dict) and query.get("street") == "123 Main St":
            m = mocker.MagicMock()
            m.latitude = 40.0
            m.longitude = -75.0
            return m
        return None # Fallback for others

    mock_geolocator.geocode.side_effect = mock_geocode
    
    region_config = {"name": "Test", "zips": ["20723"]}
    
    # Test with interactive mode (headless=False)
    mocker.patch("time.sleep")
    data = gas.scrape_gasbuddy(region_config, headless=False)
    
    assert mock_wait.called
    # Costco should be filtered, PriceTrends should be filtered, p5 should be filtered
    assert len(data) == 3
    stations = [d.station_name for d in data]
    assert "Royal Farms" in stations
    assert "Mystery Station" in stations
    assert "Shell" in stations # Cleaned from "Shell 1.2 mi"
    
    # Test Geocoding Cache hit
    data2 = gas.scrape_gasbuddy(region_config, headless=True)
    assert len(data2) == 3

def test_scrape_gasbuddy_geocoding_error(mocker):
    mocker.patch("gas_scraper.main.load_geo_cache", return_value=GeocodeCache(root={}))
    mock_driver = mocker.MagicMock()
    mocker.patch("gas_scraper.main.init_driver", return_value=mock_driver)
    
    mock_bs = mocker.patch("gas_scraper.main.BeautifulSoup")
    mock_soup = mocker.MagicMock()
    mock_bs.return_value = mock_soup
    
    def create_price_node(p_str):
        n = mocker.MagicMock()
        n.get_text.return_value = p_str
        return n
    p1 = create_price_node("$ 3.50")
    c1 = mocker.MagicMock(name="card")
    c1.name = "div"
    c1.get.return_value = []
    c1.find.side_effect = lambda tag, **kwargs: mocker.MagicMock(get_text=lambda strip=True: "Shell") if tag == "h3" else None
    c1.get_text.return_value = "Shell\n123 Main St\n$ 3.50"
    p1.parent = c1
    mock_soup.find_all.return_value = [p1]

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
    mock_bs = mocker.patch("gas_scraper.main.BeautifulSoup")
    mock_soup = mocker.MagicMock()
    mock_bs.return_value = mock_soup
    def create_price_node(p_str):
        n = mocker.MagicMock()
        n.get_text.return_value = p_str
        return n
    p1 = create_price_node("$ 3.50")
    p1.parent = mocker.MagicMock()
    p1.parent.side_effect = Exception("Parsing error") # This will trigger generic Exception in scrape_gasbuddy
    mock_soup.find_all.return_value = [p1]
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
    mock_bs = mocker.patch("gas_scraper.main.BeautifulSoup")
    mock_nominatim = mocker.patch("gas_scraper.main.Nominatim")
    
    mock_driver = mocker.MagicMock()
    mock_init_driver.return_value = mock_driver
    
    # Simulate first zip success, second zip failure (Timeout)
    def side_effect(url):
        if "21044" in url:
            raise Exception("Timeout")
        return None
    
    mock_driver.get.side_effect = side_effect
    
    # Mock soup to return a price for the successful zip
    mock_soup = mocker.MagicMock()
    mock_bs.return_value = mock_soup
    mock_soup.find_all.return_value = ["$ 3.50"]
    
    # Mock parser to return data
    mock_parse = mocker.patch("gas_scraper.main.parse_station_card")
    mock_parse.return_value = GasStation(
        Station="S1", Address="A1", Zip="20723", City="C1", 
        Base=3.50, discount_amount=0.0, Street="A1"
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
            Long=-75.0
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
    df = pd.DataFrame([{
        "Station": "Test", "Net": 3.0, "Base": 3.1, 
        "Discount": "-", "Address": "Addr", "City": "City"
    }])
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
            Station="S1", Address="A1", City="C1", Zip="20723",
            Base=3.1, discount_amount=0.1, Discount="D1"
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
    monkeypatch.setitem(sys.modules, 'uszipcode', None)
    # Reloading gas with uszipcode missing
    importlib.reload(gas)
    assert gas.HAS_RADIUS_LIB is False
    # Restore gas for other tests
    importlib.reload(gas)
