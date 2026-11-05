import pytest
from gas_scraper.browser import init_driver, get_chrome_major_version


def test_init_driver_windowed(mocker):
    # Setup mocks using pytest-mock
    mock_options = mocker.patch("gas_scraper.browser.uc.ChromeOptions")
    mock_chrome = mocker.patch("gas_scraper.browser.uc.Chrome")
    mock_stealth = mocker.patch("gas_scraper.browser.stealth")
    mock_version = mocker.patch("gas_scraper.browser.get_chrome_major_version", return_value=156)

    mock_opt_instance = mock_options.return_value

    driver = init_driver(headless=False)

    # Check for windowed specific option
    mock_opt_instance.add_argument.assert_any_call("--start-maximized")

    # Check for prefs
    mock_opt_instance.add_experimental_option.assert_called_once()

    mock_chrome.assert_called_once_with(
        options=mock_opt_instance,
        headless=False,
        use_subprocess=True,
        version_main=156,
        browser_executable_path=None,
    )
    mock_stealth.assert_called_once()
    assert driver == mock_chrome.return_value


def test_init_driver_headless(mocker):
    # Setup mocks using pytest-mock
    mock_options = mocker.patch("gas_scraper.browser.uc.ChromeOptions")
    mock_chrome = mocker.patch("gas_scraper.browser.uc.Chrome")
    mock_stealth = mocker.patch("gas_scraper.browser.stealth")
    mock_version = mocker.patch("gas_scraper.browser.get_chrome_major_version", return_value=156)

    mock_opt_instance = mock_options.return_value

    driver = init_driver(headless=True)

    # Check for headless specific options
    mock_opt_instance.add_argument.assert_any_call("--no-sandbox")
    mock_opt_instance.add_argument.assert_any_call("--disable-dev-shm-usage")

    mock_chrome.assert_called_once_with(
        options=mock_opt_instance,
        headless=True,
        use_subprocess=True,
        version_main=156,
        browser_executable_path=None,
    )
    mock_stealth.assert_called_once()
    assert driver == mock_chrome.return_value
