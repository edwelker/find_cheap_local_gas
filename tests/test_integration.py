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

    # Mock the page source to simulate a GasBuddy result using the corrected, real-world structure
    mock_driver.page_source = """
    <div class="panel__panel___3Q2zW panel__white___19KTz colors__bgWhite___1stjL panel__bordered___1Xe-S panel__rounded___2etNE GenericStationListItem-module__station___1O4vF" id="75337">
        <div class="GenericStationListItem-module__stationListItem___3Jmn4">
            <div class="StationDisplay-module__mainInfoColumn___1ZBwz StationDisplay-module__column___3h4Wf">
                <h3 class="header__header3___1b1oq header__header___1zII0 header__midnight___1tdCQ header__snug___lRSNK StationDisplay-module__stationNameHeader___1A2q8">
                    <a style="color: inherit; font-weight: 700; text-decoration: inherit" href="/station/75337">Integration</a><span> </span>
                </h3>
                <div class="StationDisplay-module__address___2_c7v">
                    123 Test St<br />Laurel, MD
                </div>
            </div>
            <div class="GenericStationListItem-module__priceCard___27wng">
                <span class="text__xl___2MXGo text__left___1iOw3 StationDisplayPrice-module__price___3rARL">$3.00</span>
            </div>
        </div>
    </div>
    <div class="GenericStationListItem-module__station___PHANTOM">
        <p>This phantom div should be ignored by the parser.</p>
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
        assert "Integration" in result.output        
        # Check for generated files
        files = os.listdir(".")
        assert any(f.startswith("latest_Single_Zip_20723") for f in files)
