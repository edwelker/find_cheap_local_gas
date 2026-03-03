from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium_stealth import stealth

def init_driver(headless=False):
    """
    Initializes a Chrome webdriver with stealth options to avoid bot detection.
    """
    print(f"\n🚀 Launching Browser ({'Headless' if headless else 'Windowed'} mode)...")
    options = Options()

    # PERFORMANCE: Block images but allow CSS/JS for correct rendering
    # Only applicable in headless mode for maximum speed
    if headless:
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        
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
    else:
        options.add_argument("--start-maximized")

    # Common options to avoid detection
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(options=options)

    # RELIABILITY: Use selenium-stealth to further hide the bot footprint
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
