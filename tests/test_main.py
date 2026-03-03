import pytest
import re
import os
import sys
import importlib
import pandas as pd
from unittest.mock import MagicMock, patch
import gas_scraper.main as gas
import gas_scraper.config as config
from gas_scraper.parser import clean_address, get_state_hint

# --- CLI UI HELPERS TESTS ---

def test_display_region_menu(capsys):
    gas.display_region_menu()
    captured = capsys.readouterr()
    assert "--- SELECT REGION ---" in captured.out
    assert "1. Maryland" in captured.out
    assert "4. CUSTOM SEARCH" in captured.out

def test_get_user_choice(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "1")
    assert gas.get_user_choice() == "1"

def test_get_user_zip(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "20723")
    assert gas.get_user_zip() == "20723"

def test_wait_for_user_to_confirm_prices(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda _: "")
    gas.wait_for_user_to_confirm_prices("20723")
    captured = capsys.readouterr()
    assert "👉 ACTION REQUIRED for 20723" in captured.out

# --- ZIP RADIUS TESTS ---

@patch("gas_scraper.main.SearchEngine")
@patch("gas_scraper.main.HAS_RADIUS_LIB", True)
def test_calculate_radius_zips(mock_search_engine):
    mock_engine_instance = MagicMock()
    mock_search_engine.return_value = mock_engine_instance
    
    # Mock results
    res1 = MagicMock()
    res1.zipcode = "20723"
    res1.population = 1000
    res1.major_city = "Scaggsville"
    
    res2 = MagicMock()
    res2.zipcode = "21044"
    res2.population = 2000
    res2.major_city = "Columbia"
    
    mock_engine_instance.by_zipcode.return_value.radius.return_value = [res1, res2]
    
    zips = gas.calculate_radius_zips("20723", miles=15)
    assert "20723" in zips
    assert "21044" in zips
    assert len(zips) == 2

@patch("gas_scraper.main.HAS_RADIUS_LIB", False)
def test_calculate_radius_zips_no_lib():
    # This should print a warning and return just the center zip
    zips = gas.calculate_radius_zips("20723")
    assert zips == ["20723"]

@patch("gas_scraper.main.SearchEngine")
@patch("gas_scraper.main.HAS_RADIUS_LIB", True)
def test_calculate_radius_zips_no_results(mock_search_engine):
    mock_engine_instance = MagicMock()
    mock_search_engine.return_value = mock_engine_instance
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

@patch("gas_scraper.main.calculate_radius_zips")
def test_get_region_choice_custom(mock_calc):
    mock_calc.return_value = ["20723", "21044"]
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
    with patch("gas_scraper.main.calculate_radius_zips") as mock_calc:
        mock_calc.return_value = ["20723"]
        res = gas.get_region_choice()
        assert res["name"] == "Custom_Radius_20723"

# --- SCRAPER TESTS ---

@patch("gas_scraper.main.init_driver")
@patch("gas_scraper.main.Nominatim")
@patch("gas_scraper.main.BeautifulSoup")
@patch("gas_scraper.main.wait_for_user_to_confirm_prices")
def test_scrape_gasbuddy_comprehensive(mock_wait, mock_bs, mock_nominatim, mock_init_driver):
    mock_driver = MagicMock()
    mock_init_driver.return_value = mock_driver
    
    mock_geolocator = MagicMock()
    mock_nominatim.return_value = mock_geolocator
    
    # Mock BeautifulSoup to find prices and cards
    mock_soup = MagicMock()
    mock_bs.return_value = mock_soup
    
    class PriceString(str):
        pass

    # 1. Normal Station (Royal Farms)
    p1 = PriceString("$ 3.50")
    c1 = MagicMock()
    c1.name = "div"
    c1.get.return_value = ["SomeClass"]
    c1.find.side_effect = lambda tag, **kwargs: MagicMock(get_text=lambda strip=True: "Royal Farms") if tag == "h3" else None
    c1.get_text.return_value = "Royal Farms\n123 Main St\n$ 3.50"
    p1.parent = c1

    # 2. Blocklisted Station (Costco)
    p2 = PriceString("$ 3.30")
    c2 = MagicMock()
    c2.name = "div"
    c2.get.return_value = ["SomeClass"]
    c2.find.side_effect = lambda tag, **kwargs: MagicMock(get_text=lambda strip=True: "Costco") if tag == "h3" else None
    c2.get_text.return_value = "Costco\n456 Oak Ave\n$ 3.30"
    p2.parent = c2

    # 3. PriceTrends Card (Should be ignored)
    p3 = PriceString("$ 3.40")
    c3 = MagicMock()
    c3.name = "div"
    c3.get.return_value = ["PriceTrendsContainer"]
    c3.find.return_value = None
    c3.get_text.return_value = "Price Trends\n$ 3.40"
    p3.parent = c3

    # 4. Unknown Address Geocoding Fallback
    p4 = PriceString("$ 3.60")
    c4 = MagicMock()
    c4.name = "div"
    c4.get.return_value = []
    c4.find.side_effect = lambda tag, **kwargs: MagicMock(get_text=lambda strip=True: "Mystery Station") if tag == "h3" else None
    c4.get_text.return_value = "Mystery Station\nNo Address Here\n$ 3.60"
    p4.parent = c4
    
    # 5. Card not found (depth limit reached)
    p5 = PriceString("$ 3.70")
    p5.parent = MagicMock()
    p5.parent.name = "span"
    p5.parent.get.return_value = []
    p5.parent.find.return_value = None
    # Chain of parents that never find a card with h3
    curr = p5.parent
    for _ in range(10):
        curr.parent = MagicMock()
        curr.parent.name = "span"
        curr.parent.get.return_value = []
        curr.parent.find.return_value = None
        curr = curr.parent

    # 6. Station name with miles (should be cleaned)
    p6 = PriceString("$ 3.80")
    c6 = MagicMock()
    c6.name = "div"
    c6.get.return_value = None # Hits line 358: if classes and any(...)
    c6.find.side_effect = lambda tag, **kwargs: MagicMock(get_text=lambda strip=True: "Shell 1.2 mi") if tag == "h3" else None
    c6.get_text.return_value = "Shell 1.2 mi\n789 Pine Pike\n$ 3.80"
    p6.parent = c6

    mock_soup.find_all.return_value = [p1, p2, p3, p4, p5, p6]
    
    # Mock Geocoding
    def mock_geocode(query):
        if isinstance(query, dict) and query.get("street") == "123 Main St":
            m = MagicMock()
            m.latitude = 40.0
            m.longitude = -75.0
            return m
        return None # Fallback for others

    mock_geolocator.geocode.side_effect = mock_geocode
    
    region_config = {"name": "Test", "zips": ["20723"]}
    
    # Test with interactive mode (headless=False)
    with patch("time.sleep"):
        data = gas.scrape_gasbuddy(region_config, headless=False)
    
    assert mock_wait.called
    # Costco should be filtered, PriceTrends should be filtered, p5 should be filtered
    assert len(data) == 3
    stations = [d["Station"] for d in data]
    assert "Royal Farms" in stations
    assert "Mystery Station" in stations
    assert "Shell" in stations # Cleaned from "Shell 1.2 mi"
    
    # Test Geocoding Cache hit
    with patch("time.sleep"):
        data2 = gas.scrape_gasbuddy(region_config, headless=True)
        assert len(data2) == 3

@patch("gas_scraper.main.init_driver")
def test_scrape_gasbuddy_geocoding_error(mock_init_driver):
    mock_driver = MagicMock()
    mock_init_driver.return_value = mock_driver
    
    with patch("gas_scraper.main.BeautifulSoup") as mock_bs:
        mock_soup = MagicMock()
        mock_bs.return_value = mock_soup
        
        class PriceString(str): pass
        p1 = PriceString("$ 3.50")
        c1 = MagicMock(name="card")
        c1.name = "div"
        c1.get.return_value = []
        c1.find.side_effect = lambda tag, **kwargs: MagicMock(get_text=lambda strip=True: "Shell") if tag == "h3" else None
        c1.get_text.return_value = "Shell\n123 Main St\n$ 3.50"
        p1.parent = c1
        mock_soup.find_all.return_value = [p1]

        with patch("gas_scraper.main.Nominatim") as mock_nom:
            mock_geo = MagicMock()
            mock_nom.return_value = mock_geo
            mock_geo.geocode.side_effect = Exception("Service Down")
            
            with patch("time.sleep"):
                data = gas.scrape_gasbuddy({"name": "T", "zips": ["20723"]}, headless=True)
                assert len(data) == 1
                assert data[0]["Lat"] is None

@patch("gas_scraper.main.init_driver")
def test_scrape_gasbuddy_parsing_error(mock_init_driver):
    mock_driver = MagicMock()
    mock_init_driver.return_value = mock_driver
    with patch("gas_scraper.main.BeautifulSoup") as mock_bs:
        mock_soup = MagicMock()
        mock_bs.return_value = mock_soup
        class PriceString(str): pass
        p1 = PriceString("$ 3.50")
        p1.parent = MagicMock()
        p1.parent.side_effect = Exception("Parsing error") # This will trigger generic Exception in scrape_gasbuddy
        mock_soup.find_all.return_value = [p1]
        with patch("time.sleep"):
            data = gas.scrape_gasbuddy({"name": "T", "zips": ["20723"]}, headless=True)
            assert len(data) == 0

from click.testing import CliRunner

# --- MAIN TESTS ---

@patch("gas_scraper.main.scrape_gasbuddy")
@patch("os.makedirs")
@patch("os.path.exists")
@patch("pandas.DataFrame.to_csv")
def test_main_success(mock_to_csv, mock_exists, mock_makedirs, mock_scrape):
    mock_scrape.return_value = [
        {
            "City": "Scaggsville",
            "Zip": "20723",
            "Station": "Royal Farms",
            "Address": "123 Main St, 20723",
            "Base": 3.50,
            "Net": 3.40,
            "Discount": "Royal Farms",
            "Lat": 40.0,
            "Long": -75.0
        }
    ]
    mock_exists.return_value = True
    
    runner = CliRunner()
    result = runner.invoke(gas.main, ["1", "--headless"])
    
    assert result.exit_code == 0
    assert "✅ DATA COLLECTED" in result.output
    assert mock_to_csv.called

@patch("gas_scraper.main.scrape_gasbuddy")
def test_main_no_data(mock_scrape):
    mock_scrape.return_value = []
    
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

@patch("gas_scraper.main.scrape_gasbuddy")
def test_main_single_zip(mock_scrape):
    mock_scrape.return_value = []
    runner = CliRunner()
    result = runner.invoke(gas.main, ["--zip", "20723", "--headless"])
    
    assert result.exit_code == 0
    # Verify that scrape_gasbuddy was called with a config containing only the specified zip
    args, kwargs = mock_scrape.call_args
    assert args[0]["zips"] == ["20723"]
    assert args[0]["name"] == "Single_Zip_20723"

# --- IMPORT TESTS (TRICKY) ---

def test_import_no_uszipcode():
    with patch.dict(sys.modules, {'uszipcode': None}):
        # Reloading gas with uszipcode missing
        importlib.reload(gas)
        assert gas.HAS_RADIUS_LIB is False
    # Restore gas for other tests
    importlib.reload(gas)
