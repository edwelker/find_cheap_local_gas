import pytest
from unittest.mock import MagicMock, patch
from gas_scraper.browser import init_driver

@patch("gas_scraper.browser.webdriver.Chrome")
@patch("gas_scraper.browser.Options")
def test_init_driver_windowed(mock_options, mock_chrome):
    mock_opt_instance = MagicMock()
    mock_options.return_value = mock_opt_instance
    
    driver = init_driver(headless=False)
    
    # Check if common options are set
    mock_opt_instance.add_argument.assert_any_call("--disable-blink-features=AutomationControlled")
    # Check for windowed specific option
    mock_opt_instance.add_argument.assert_any_call("--start-maximized")
    
    assert driver == mock_chrome.return_value

@patch("gas_scraper.browser.webdriver.Chrome")
@patch("gas_scraper.browser.Options")
def test_init_driver_headless(mock_options, mock_chrome):
    mock_opt_instance = MagicMock()
    mock_options.return_value = mock_opt_instance
    
    driver = init_driver(headless=True)
    
    # Check for headless specific options
    mock_opt_instance.add_argument.assert_any_call("--headless")
    mock_opt_instance.add_argument.assert_any_call("--no-sandbox")
    
    assert driver == mock_chrome.return_value
