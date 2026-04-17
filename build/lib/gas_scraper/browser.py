import os

import undetected_chromedriver as uc
from selenium_stealth import stealth
from loguru import logger


def init_driver(headless=False):
    """
    Initializes an undetected Chrome webdriver to bypass advanced bot detection.
    """
    logger.info(
        f"\n🚀 Launching Browser ({'Headless' if headless else 'Windowed'} mode)..."
    )

    # RELIABILITY: Using undetected_chromedriver (uc) instead of standard Selenium
    # uc patches the chrome binary to remove 'cdc_' and other bot fingerprints.
    options = uc.ChromeOptions()

    # PERFORMANCE: Block images but allow CSS/JS for correct rendering
    # Prefs must be set before driver initialization
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.default_content_setting_values.notifications": 2,
        "profile.managed_default_content_settings.stylesheets": 1,
        "profile.managed_default_content_settings.cookies": 1,
        "profile.managed_default_content_settings.javascript": 1,
        "profile.managed_default_content_settings.plugins": 2,
        "profile.managed_default_content_settings.popups": 2,
        "profile.managed_default_content_settings.geolocation": 2,
    }
    options.add_experimental_option("prefs", prefs)

    if not headless:
        options.add_argument("--start-maximized")
    else:
        # Note: 'headless' is also passed directly to the uc.Chrome constructor
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")

    # Initialize the patched driver
    # PERFORMANCE: Specify version to avoid mismatch issues
    chrome_binary = os.environ.get("CHROME_BINARY")
    driver = uc.Chrome(
        options=options,
        headless=headless,
        use_subprocess=True,
        version_main=145,
        browser_executable_path=chrome_binary if chrome_binary else None,
    )

    # RELIABILITY: Secondary layer using selenium-stealth to spoof hardware/browser traits
    stealth(
        driver,
        languages=["en-US", "en"],
        vendor="Google Inc.",
        platform="Win32",
        webgl_vendor="Intel Inc.",
        renderer="Intel Iris OpenGL Engine",
        fix_hairline=True,
    )

    return driver
