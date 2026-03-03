import gas_scraper.config as config


def test_config_data_exists():
    assert config.REGION_DATA is not None
    assert config.BLOCKLIST is not None
    assert config.DISCOUNTS is not None
    assert config.ZIP_MAP is not None


def test_zip_map_derivation():
    # Check if a known zip from REGION_DATA is in ZIP_MAP
    assert "20723" in config.ZIP_MAP
    assert config.ZIP_MAP["20723"] == "Scaggsville / Laurel"

    # Check another region
    assert "11901" in config.ZIP_MAP
    assert config.ZIP_MAP["11901"] == "Riverhead"


def test_blocklist_content():
    assert "Costco" in config.BLOCKLIST
    assert "GasBuddy" in config.BLOCKLIST


def test_discounts_content():
    assert "Royal Farms" in config.DISCOUNTS
    assert config.DISCOUNTS["Royal Farms"] == 0.10
