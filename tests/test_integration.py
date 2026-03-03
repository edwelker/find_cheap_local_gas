import pytest
from click.testing import CliRunner
import gas_scraper.main as gas
import os

def test_integration_single_zip_flow(mocker):
    """
    Integration test verifying the full flow for a single zip code.
    Mocks only the external dependencies (Browser/Geocoder) but runs
    the full CLI and logic path.
    """
    # 1. Mock Browser/Driver
    mocker.patch("time.sleep")
    mock_init_driver = mocker.patch("gas_scraper.main.init_driver")
    mock_driver = mocker.MagicMock()
    mock_init_driver.return_value = mock_driver
    
    # PERFORMANCE: Mock WebDriverWait to avoid 20s timeouts in tests
    mocker.patch("gas_scraper.main.WebDriverWait")
    mocker.patch("gas_scraper.main.EC")

    # Mock the page source to simulate a GasBuddy result
    mock_driver.page_source = """
    <div class="GenericStationListItem-module__station">
        <h3><a href="#">Integration Test Station</a></h3>
        <div class="StationDisplay-module__address">123 Test St</div>
        <div class="StationDisplayPrice-module__price"><span>$3.00</span></div>
    </div>
    """
    mock_driver.title = "GasBuddy"
    
    # 2. Mock Geocoder
    mock_nominatim = mocker.patch("gas_scraper.main.Nominatim")
    mock_geolocator = mocker.MagicMock()
    mock_nominatim.return_value = mock_geolocator
    mock_geolocator.geocode.return_value = None 

    # 3. Run the CLI
    runner = CliRunner()
    # Use isolated filesystem to avoid polluting real history/root
    with runner.isolated_filesystem():
        result = runner.invoke(gas.main, ["--zip", "20723", "--headless"])
        
        # 4. Assertions
        assert result.exit_code == 0
        assert "DATA COLLECTED" in result.output
        assert "Integration Test Station" in result.output
        
        # Check for generated files
        files = os.listdir(".")
        assert any(f.startswith("latest_Single_Zip_20723") for f in files)
