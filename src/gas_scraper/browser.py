from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def init_driver(headless=False):
    """
    Initializes a Chrome webdriver with options to avoid bot detection.
    """
    print(f"\n🚀 Launching Browser ({'Headless' if headless else 'Windowed'} mode)...")
    options = Options()

    # Common options to avoid bot detection
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    if headless:
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
    else:
        options.add_argument("--start-maximized")

    return webdriver.Chrome(options=options)
