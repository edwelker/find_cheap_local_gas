import pytest
from click.testing import CliRunner
import gas_scraper.main as gas
import os


@pytest.mark.live
def test_live_scrape_single_zip():
    """
    REAL INTEGRATION TEST:
    Actually launches the browser, hits GasBuddy, and parses results.
    Run this with: pytest -m live
    """
    runner = CliRunner()
    with runner.isolated_filesystem():
        # Run real scrape for a single zip
        result = runner.invoke(gas.main, ["--zip", "20723", "--headless"])

        assert result.exit_code == 0
        assert "✅ DATA COLLECTED" in result.output

        # Verify real data was found (at least one station)
        assert "Station" in result.output
        assert "Address" in result.output

        # Verify files
        files = os.listdir(".")
        assert any(f.startswith("latest_Single_Zip_20723") for f in files)
