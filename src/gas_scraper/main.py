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
    # This ensures we hit the busy areas with gas stations, not empty farmland
    neighbors.sort(key=lambda x: x["pop"], reverse=True)

    # Always include the requested center zip at the start
    top_zips = [center_zip]
    count = 0
    seen = {center_zip} # PERFORMANCE: Deduplicate zips to avoid redundant browser navigations
    for n in neighbors:
        if count >= 4:
            break  # Limit to +4 neighbors (5 total)
        if n["zip"] not in seen:
            top_zips.append(n["zip"])
            seen.add(n["zip"])
            count += 1

    print(f"   Targeting {len(top_zips)} key zip codes: {', '.join(top_zips)}")
    return top_zips


# --- 3. CLI UI HELPERS ---

def display_region_menu():
    print("\n--- SELECT REGION ---")
    for key, val in REGION_DATA.items():
        print(f"{key}. {val['name']}")
    print("4. CUSTOM SEARCH (Radius Calculation)")


def get_user_choice():
    return input("Enter number: ").strip()


def get_user_zip():
    return input("Enter Center Zip Code: ").strip()


def wait_for_user_to_confirm_prices(zip_code):
    print(f"👉 ACTION REQUIRED for {zip_code}:")
    print("   1. If Cloudflare checks you, click the box.")
    print("   2. Wait for the list of stations to appear.")
    input("   3. Press ENTER here once the prices are visible... ")


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

    # Default to 1 if invalid
    if choice not in REGION_DATA:
        choice = "1"

    selected = REGION_DATA[choice]
    return {
        "name": selected["name"],
        "zips": list(selected["zips"].keys()),
    }


def scrape_gasbuddy(region_config, headless=False):
    driver = init_driver(headless=headless)

    # PERFORMANCE: Initialize geocoding cache from disk to skip redundant API calls/delays
    geolocator = Nominatim(user_agent="gas_scraper_bot_v1", timeout=10)
    geo_cache = load_geo_cache()

    scraped_data = []

    try:
        # PERFORMANCE: Deduplicate zip codes to avoid redundant navigations
        zips = list(dict.fromkeys(region_config["zips"]))
        
        for zip_code in zips:
            city_name = ZIP_MAP.get(zip_code, zip_code)
            print(f"\n📍 Navigating to: {city_name} ({zip_code})...")

            # PERFORMANCE/RELIABILITY: Humanizing delay between zips to avoid Cloudflare/Bot detection
            if zips.index(zip_code) > 0:
                delay = random.uniform(3.0, 7.0)
                print(f"   (Waiting {delay:.1f}s to look human...)")
                time.sleep(delay)

            url = f"https://www.gasbuddy.com/home?search={zip_code}&fuel=1"
            
            # --- RETRY LOGIC FOR PAGE LOAD ---
            max_retries = 2
            success = False
            for attempt in range(max_retries + 1):
                try:
                    driver.get(url)
                    # Check if we actually landed on the right page or a block page
                    title = driver.title
                    if "GasBuddy" not in title:
                        print(f"   ⚠️  Unexpected page title: '{title}'. Possible block.")
                        # DIAGNOSTIC: Print snippet of body to see block type
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
                        try:
                            print(f"      Current URL: {driver.current_url}")
                            print(f"      Page Title:  {driver.title}")
                        except:
                            pass

            if not success:
                continue

            try:
                # --- HUMAN INTERVENTION / WAIT ---
                if not headless:
                    wait_for_user_to_confirm_prices(zip_code)
                else:
                    # PERFORMANCE: Smart Wait proceeds as soon as prices appear (replaces fixed 15s sleep)
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
                        scraped_data.append(station_data)
            except Exception as e:
                print(f"   ❌ Error parsing {zip_code}: {e}")
                continue

    finally:
        # PERFORMANCE: Close browser before geocoding to free up system resources
        driver.quit()

    # PERFORMANCE: Defer geocoding to the end to avoid blocking browser loop
    # Deduplicate results by Station/Address to avoid geocoding same station twice
    unique_stations = { (s["Station"], s["Address"]): s for s in scraped_data }.values()
    
    initial_cache_size = len(geo_cache)
    final_data = geocode_stations(list(unique_stations), geolocator, geo_cache)
    
    # PERFORMANCE: Only save if new entries were added to minimize disk writes
    if len(geo_cache) > initial_cache_size:
        save_geo_cache(geo_cache)

    return final_data


def display_results(df):
    """
    Prints the collected gas price data in both grouped and sorted views.
    """
    pd.set_option("display.max_rows", None)
    pd.set_option("display.width", 1000)
    cols = ["Station", "Net", "Base", "Discount", "Address", "City"]

    # 1. Grouped View
    print("\n" + "=" * 80)
    print("📍 VIEW 1: GROUPED BY CITY")
    print("=" * 80)
    grouped = df.sort_values(by=["City", "Net"])
    for city, group in grouped.groupby("City"):
        print(f"\n>> {city}")
        print("-" * 80)
        print(group[cols].to_string(index=False))

    # 2. Overall Cheapest View
    print("\n" + "=" * 80)
    print("🏆 VIEW 2: CHEAPEST OVERALL (SORTED)")
    print("=" * 80)
    df_sorted = df.sort_values(by="Net", ascending=True)
    print(df_sorted[cols].to_string(index=False))
    print("\n")


import click

@click.command()
@click.argument("choice", required=False)
@click.argument("zip_code", required=False)
@click.option("--headless", is_flag=True, help="Run browser in headless mode.")
@click.option("--zip", "target_zip", help="Search a single specific zip code only (overrides CHOICE).")
def main(choice, zip_code, headless, target_zip):
    """
    Gas Price Scraper CLI.
    CHOICE: Region number (1-3) or 4 for custom radius.
    ZIP_CODE: Center zip for custom radius search.
    """
    # Detect if running in GitHub Actions or requested via CLI
    is_automated = (os.environ.get("GITHUB_ACTIONS") == "true") or headless

    if target_zip:
        region = {"name": f"Single_Zip_{target_zip}", "zips": [target_zip]}
    else:
        region = get_region_choice(choice, zip_code)

    # --- PRE-CHECK: Ensure history directory exists ---
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

    df = pd.DataFrame(data)
    # Already deduplicated in scrape_gasbuddy, but safe to keep
    df = df.drop_duplicates(subset=["Station", "Address"])

    # --- SAVE TO HISTORY (Only for full regions/radius, not single zips) ---
    is_single_zip = safe_name.startswith("Single_Zip_")
    filename = None

    if not is_single_zip:
        # Use Eastern Time for consistent naming
        now = datetime.datetime.now(ZoneInfo("America/New_York"))
        date_str = now.strftime("%Y-%m-%d_%H-%M")
        filename = os.path.join(history_dir, f"gas_{safe_name}_{date_str}.csv")
        df.to_csv(filename, index=False)

    # Save a "latest" version in the root directory for easy access by external sites
    latest_filename = f"latest_{safe_name}.csv"
    df.to_csv(latest_filename, index=False)

    print("\n" + "=" * 80)
    print("✅ DATA COLLECTED")
    print("=" * 80)
    if filename:
        print(f"Historical File: {os.path.abspath(filename)}")
    print(f"Latest Pointer:   {os.path.abspath(latest_filename)}")

    display_results(df)


if __name__ == "__main__":
    main()
