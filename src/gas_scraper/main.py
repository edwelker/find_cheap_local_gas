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
from .parser import parse_station_card, load_geo_cache, save_geo_cache, geocode_stations
from .user_interface import (
    display_region_menu, 
    get_user_choice, 
    get_user_zip, 
    wait_for_user_to_confirm_prices, 
    display_results
)
from bs4 import BeautifulSoup
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut

# --- LIBRARY CHECK for Radius Search ---
try:
    from uszipcode import SearchEngine
    HAS_RADIUS_LIB = True
except ImportError:
    HAS_RADIUS_LIB = False

from .config import REGION_DATA, ZIP_MAP, BLOCKLIST, DISCOUNTS

# --- 2. CONFIGURATION: RADIUS SEARCH ---
def calculate_radius_zips(center_zip, miles=15):
    """
    Calculates neighbors within N miles using uszipcode database.
    Returns the top 5 most populated zips to avoid scanning 50+ locations.
    """
    if not HAS_RADIUS_LIB:
        print("\n⚠️  'uszipcode' library not found.")
        print("   Running just the single zip code.")
        print("   To enable radius calculation, run: pip install uszipcode")
        return [center_zip]

    print(f"\n📐 Calculating zips within {miles} miles of {center_zip}...")
    search = SearchEngine()

    # 1. Get neighbors
    results = search.by_zipcode(center_zip).radius(radius=miles, returns=50)

    if not results:
        print("   No results found for that zip. Checking just the center.")
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

    print(f"   Targeting {len(top_zips)} key zip codes: {', '.join(top_zips)}")
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


def fetch_gas_prices_for_zip(driver, zip_code, city_name, headless=False):
    """
    Handles the actual navigation, retries, and parsing for a single zip code.
    Returns a list of station data dicts.
    """
    url = f"https://www.gasbuddy.com/home?search={zip_code}&fuel=1"
    
    # --- RETRY LOGIC FOR PAGE LOAD ---
    max_retries = 2
    success = False
    for attempt in range(max_retries + 1):
        try:
            driver.get(url)
            title = driver.title
            if "GasBuddy" not in title:
                print(f"   ⚠️  Unexpected page title: '{title}'. Possible block.")
                try:
                    snippet = driver.page_source[:500].replace("\n", " ")
                    print(f"      Source Snippet: {snippet}...")
                except:
                    pass
            
            success = True
            break
        except Exception as e:
            if attempt < max_retries:
                print(f"   ⚠️  {type(e).__name__} loading {zip_code}. Retrying ({attempt+1}/{max_retries})...")
                time.sleep(5)
            else:
                print(f"   ❌ Failed to load {zip_code} after {max_retries+1} attempts: {e}")
                return []

    if not success:
        return []

    zip_scraped_data = []
    try:
        # --- WAIT FOR CONTENT ---
        if not headless:
            wait_for_user_to_confirm_prices(zip_code)
        else:
            print("   Waiting for prices to load...")
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.XPATH, "//*[contains(text(), '$')]"))
                )
            except Exception:
                print("   ⚠️  Timed out waiting for prices. Attempting to parse anyway...")

        soup = BeautifulSoup(driver.page_source, "html.parser")

        # Parse Prices
        price_regex = re.compile(r"\$\s*([2-5]\.\d{2})")
        found_prices = soup.find_all(string=price_regex)

        print(f"   (Found {len(found_prices)} prices)")

        for price_node in found_prices:
            station_data = parse_station_card(price_node, zip_code, city_name)
            if station_data:
                zip_scraped_data.append(station_data)
                
    except Exception as e:
        print(f"   ❌ Error parsing {zip_code}: {e}")

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
            print(f"\n📍 Navigating to: {city_name} ({zip_code})...")

            if zips.index(zip_code) > 0:
                delay = random.uniform(3.0, 7.0)
                print(f"   (Waiting {delay:.1f}s to look human...)")
                time.sleep(delay)

            zip_data = fetch_gas_prices_for_zip(driver, zip_code, city_name, headless=headless)
            scraped_data.extend(zip_data)

    finally:
        driver.quit()

    unique_stations = { (s.station_name, s.address): s for s in scraped_data }.values()
    
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
@click.option("--zip", "target_zip", help="Search a single specific zip code only (overrides CHOICE).")
def main(choice, zip_code, headless, target_zip):
    """
    Gas Price Scraper CLI.
    """
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
        print("❌ No data found.")
        return

    # PERFORMANCE: Deduplicate and convert to DataFrame using Pydantic aliases (for UI/CSV)
    # data is a list of GasStation objects
    unique_data = { (s.station_name, s.address): s for s in data }.values()
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
    console.print(Panel(info_text, title="[bold green]✅ DATA COLLECTED[/]", border_style="green", expand=False))

    display_results(df)


if __name__ == "__main__":
    main()
