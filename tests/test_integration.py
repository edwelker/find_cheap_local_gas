import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock
import gas_scraper.main as gas
import os

@patch("gas_scraper.main.init_driver")
@patch("gas_scraper.main.Nominatim")
def test_integration_single_zip_flow(mock_nominatim, mock_init_driver):
    """
    Integration test verifying the full flow for a single zip code.
    Mocks only the external dependencies (Browser/Geocoder) but runs
    the full CLI and logic path.
    """
    # 1. Mock Browser/Driver
    mock_driver = MagicMock()
    mock_init_driver.return_value = mock_driver
    # Mock the page source to simulate a GasBuddy result
    mock_driver.page_source = """
    <div class="StationCard">
        <h3>Integration Test Station</h3>
        <span>123 Test St</span>
        <div class="Price"><span>$ 3.00</span></div>
    </div>
    """
    
    # 2. Mock Geocoder
    mock_geolocator = MagicMock()
    mock_nominatim.return_value = mock_geolocator
    mock_geolocator.geocode.return_value = None 

    # 3. Run the CLI
    runner = CliRunner()
    # Use isolated filesystem to avoid polluting real history/root
    with runner.isolated_filesystem():
        # Ensure the mock driver doesn't hang on time.sleep in scrape_gasbuddy
        with patch("time.sleep"):
            result = runner.invoke(gas.main, ["--zip", "20723", "--headless"])
        
        # 4. Assertions
        assert result.exit_code == 0
        assert "✅ DATA COLLECTED" in result.output
        assert "Integration Test Station" in result.output
        
        # Check for generated files
        files = os.listdir(".")
        assert any(f.startswith("latest_Single_Zip_20723") for f in files)
        
        # history folder might be created, but should NOT contain the single zip file
        if os.path.exists("history"):
            history_files = os.listdir("history")
            assert not any(f.startswith("gas_Single_Zip_20723") for f in history_files)
