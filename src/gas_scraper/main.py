import sys
import time
import re
import os
import datetime
import json
import random
from zoneinfo import ZoneInfo
import pandas as pd
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from .browser import init_driver
from .parser import (
    get_station_cards,
    parse_station_card,
    load_geo_cache,
    save_geo_cache,
    geocode_stations,
)
from .user_interface import (
    display_region_menu,
    get_user_choice,
    get_user_zip,
    wait_for_user_to_confirm_prices,
    display_results,
)
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
from selenium.common.exceptions import TimeoutException # New import for cookie banner handling
from tenacity import retry, stop_after_attempt, wait_fixed
from loguru import logger

# --- LIBRARY CHECK for Radius Search ---
try:
    from uszipcode import SearchEngine

    HAS_RADIUS_LIB = True
except ImportError:
    HAS_RADIUS_LIB = False

from .config import REGION_DATA, ZIP_MAP, BLOCKLIST, DISCOUNTS


def setup_logging():
    """Configures Loguru to handle both clean console output and detailed file logging."""
    logger.remove()
    # User Console: Clean info
    logger.add(sys.stdout, format="<level>{message}</level>", level="INFO")
    # Developer File: Detailed debug
    logger.add("scraper.log", rotation="1 MB", level="DEBUG")


# --- 2. CONFIGURATION: RADIUS SEARCH ---
def calculate_radius_zips(center_zip, miles=15):
    """
    Calculates neighbors within N miles using uszipcode database.
    Returns the top 5 most populated zips to avoid scanning 50+ locations.
    """
    if not HAS_RADIUS_LIB:
        logger.warning("⚠️  'uszipcode' library not found.")
        logger.info("   Running just the single zip code.")
        logger.info("   To enable radius calculation, run: pip install uszipcode")
        return [center_zip]

    logger.info(f"📐 Calculating zips within {miles} miles of {center_zip}...")
    search = SearchEngine()

    # 1. Get neighbors
    results = search.by_zipcode(center_zip).radius(radius=miles, returns=50)

    if not results:
        logger.warning("   No results found for that zip. Checking just the center.")
        return [center_zip]

    # 2. Convert to list of dicts for sorting
    neighbors = []
    for r in results:
        neighbors.append(
            {
                "zip": r.zipcode,
                "pop": r.population if r.population else 0,
                "city": r.major_city,
            }
        )
        # Add to global map for pretty printing later
        ZIP_MAP[r.zipcode] = r.major_city

    # 3. Sort by Population (Descending) and take Top 5
    neighbors.sort(key=lambda x: x["pop"], reverse=True)

    # Always include the requested center zip at the start
    top_zips = [center_zip]
    count = 0
    seen = {center_zip}
    for n in neighbors:
        if count >= 4:
            break
        if n["zip"] not in seen:
            top_zips.append(n["zip"])
            seen.add(n["zip"])
            count += 1

    logger.info(f"   Targeting {len(top_zips)} key zip codes: {', '.join(top_zips)}")
    return top_zips


def get_region_choice(cli_choice=None, cli_zip=None):
    if cli_choice:
        choice = cli_choice
    else:
        display_region_menu()
        choice = get_user_choice()

    if choice == "4":
        if cli_zip:
            center = cli_zip
        else:
            center = get_user_zip()
        zips = calculate_radius_zips(center, miles=15)
        return {"name": f"Custom_Radius_{center}", "zips": zips}

    if choice not in REGION_DATA:
        choice = "1"

    selected = REGION_DATA[choice]
    return {
        "name": selected["name"],
        "zips": list(selected["zips"].keys()),
    }


def _log_retry(retry_state):
    """Callback to print a message before retrying."""
    logger.warning(
        f"   ⚠️  Error loading page. Retrying ({retry_state.attempt_number}/2)..."
    )


@retry(
    stop=stop_after_attempt(3), 
    wait=wait_fixed(5), 
    before_sleep=_log_retry,
    reraise=True
)
def _get_page_with_retry(driver, url):
    """Declarative retry wrapper for driver.get()."""
    driver.get(url)

    # Check for and accept cookie banner
    try:
        accept_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
        )
        logger.info("🍪 Cookie banner detected, accepting...")
        accept_button.click()
        # Wait for the banner to disappear
        WebDriverWait(driver, 10).until_not(
            EC.presence_of_element_located((By.ID, "onetrust-banner-sdk"))
        )
        logger.info("🍪 Cookie banner accepted.")
    except TimeoutException:
        logger.debug("🍪 No cookie banner found or timed out waiting for it.")
    except Exception as e:
        logger.warning(f"Error handling cookie banner: {e}")

    title = driver.title
    if "GasBuddy" not in title:
        logger.warning(f"   ⚠️  Unexpected page title: '{title}'. Possible block.")
        logger.debug(f"Source Snippet: {driver.page_source[:500].replace('\n', ' ')}")


def fetch_gas_prices_for_zip(driver, zip_code, city_name, headless=False):
    """
    Handles the actual navigation, retries, and parsing for a single zip code.
    Returns a list of GasStation objects.
    """
    url = f"https://www.gasbuddy.com/home?search={zip_code}&fuel=1"

    try:
        _get_page_with_retry(driver, url)
    except Exception as e:
        logger.error(f"   ❌ Failed to load {zip_code} after 3 attempts: {e}")
        return []

    zip_scraped_data = []
    try:
        # --- WAIT FOR CONTENT ---
        if not headless:
            wait_for_user_to_confirm_prices(zip_code)
        else:
            logger.info("   Waiting for prices to load...")
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.XPATH, "//span[contains(text(), '$')]"))
                )
            except Exception:
                logger.warning(
                    "   ⚠️  Timed out waiting for prices. Attempting to parse anyway..."
                )

        # Find all station cards using Parsel
        page_source = driver.page_source
        cards = get_station_cards(page_source)
        logger.info(f"   (Found {len(cards)} potential stations)")

        if len(cards) == 0:
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            logger.debug(f"   [DEBUG] Number of iframes: {len(iframes)}")
            exists = "StationDisplay-module__container" in page_source
            logger.debug(f"   [DEBUG] Container class exists in source: {exists}")



        for card_sel in cards:
            station_data = parse_station_card(card_sel, zip_code, city_name)
            if station_data:
                zip_scraped_data.append(station_data)

    except Exception as e:
        logger.error(f"   ❌ Error parsing {zip_code}: {e}")

    return zip_scraped_data


def scrape_gasbuddy(region_config, headless=False):
    driver = init_driver(headless=headless)

    geolocator = Nominatim(user_agent="gas_scraper_bot_v1", timeout=10)
    geo_cache = load_geo_cache()

    scraped_data = []

    try:
        zips = list(dict.fromkeys(region_config["zips"]))

        for zip_code in zips:
            city_name = ZIP_MAP.get(zip_code, zip_code)
            logger.info(f"\n📍 Navigating to: {city_name} ({zip_code})...")

            if zips.index(zip_code) > 0:
                delay = random.uniform(3.0, 7.0)
                logger.info(f"   (Waiting {delay:.1f}s to look human...)")
                time.sleep(delay)

            zip_data = fetch_gas_prices_for_zip(
                driver, zip_code, city_name, headless=headless
            )
            scraped_data.extend(zip_data)

    finally:
        driver.quit()

    unique_stations = {(s.station_name, s.address): s for s in scraped_data}.values()

    initial_cache_size = len(geo_cache.root)
    final_data = geocode_stations(list(unique_stations), geolocator, geo_cache)

    if len(geo_cache.root) > initial_cache_size:
        save_geo_cache(geo_cache)

    return final_data


import click

from rich.console import Console
from rich.panel import Panel

console = Console()


@click.command()
@click.argument("choice", required=False)
@click.argument("zip_code", required=False)
@click.option("--headless", is_flag=True, help="Run browser in headless mode.")
@click.option(
    "--zip",
    "target_zip",
    help="Search a single specific zip code only (overrides CHOICE).",
)
def main(choice, zip_code, headless, target_zip):
    """
    Gas Price Scraper CLI.
    """
    setup_logging()
    is_automated = (os.environ.get("GITHUB_ACTIONS") == "true") or headless

    if target_zip:
        region = {"name": f"Single_Zip_{target_zip}", "zips": [target_zip]}
    else:
        region = get_region_choice(choice, zip_code)

    history_dir = "history"
    if not os.path.exists(history_dir):
        os.makedirs(history_dir)

    raw_name = region["name"]
    cleaned_name = raw_name.replace("/", "_").replace(" ", "_").replace(":", "")
    safe_name = re.sub(r"[^\w\-_]", "", cleaned_name)

    data = scrape_gasbuddy(region, headless=is_automated)

    if not data:
        logger.error("❌ No data found.")
        return

    # PERFORMANCE: Deduplicate and convert to DataFrame using Pydantic aliases (for UI/CSV)
    # data is a list of GasStation objects
    unique_data = {(s.station_name, s.address): s for s in data}.values()
    df = pd.DataFrame([s.model_dump(by_alias=True) for s in unique_data])

    is_single_zip = safe_name.startswith("Single_Zip_")
    filename = None

    if not is_single_zip:
        now = datetime.datetime.now(ZoneInfo("America/New_York"))
        date_str = now.strftime("%Y-%m-%d_%H-%M")
        filename = os.path.join(history_dir, f"gas_{safe_name}_{date_str}.csv")
        df.to_csv(filename, index=False)

    latest_filename = f"latest_{safe_name}.csv"
    df.to_csv(latest_filename, index=False)

    info_text = f"Historical File: {os.path.abspath(filename)}\n" if filename else ""
    info_text += f"Latest Pointer:   {os.path.abspath(latest_filename)}"

    console.print()
    console.print(
        Panel(
            info_text,
            title="[bold green]✅ DATA COLLECTED[/]",
            border_style="green",
            expand=False,
        )
    )

    display_results(df)


if __name__ == "__main__":
    main()
