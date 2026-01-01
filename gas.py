import sys
import time
import re
import os
import datetime
from zoneinfo import ZoneInfo
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup

# --- LIBRARY CHECK for Radius Search ---
try:
    from uszipcode import SearchEngine

    HAS_RADIUS_LIB = True
except ImportError:
    HAS_RADIUS_LIB = False

# --- 1. CONFIGURATION: REGIONS & ZIPS ---
ZIP_MAP = {
    # Maryland - Columbia/EC
    "20723": "Scaggsville / Laurel",
    "21044": "Columbia (Town Center)",
    "21045": "Columbia (East)",
    "21046": "Columbia (Guilford)",
    "21042": "Ellicott City (Central)",
    "21043": "Ellicott City (North)",
    # Maryland - Severn/Commute Corridor
    "21144": "Severn",
    "21076": "Hanover (Arundel Mills)",
    "20794": "Jessup",
    "20763": "Savage",
    # Long Island
    "11901": "Riverhead",
    "11946": "Hampton Bays",
    "11968": "Southampton",
    "11976": "Water Mill",
    "11932": "Bridgehampton",
    "11937": "East Hampton",
    "11930": "Amagansett",
    "11954": "Montauk",
    # Western Mass
    "01103": "Springfield",
    "01020": "Chicopee",
    "01040": "Holyoke",
    "01027": "Easthampton",
    "01060": "Northampton",
    "01035": "Hadley",
    "01002": "Amherst",
    "01054": "Leverett",
    "01301": "Greenfield",
    "01373": "South Deerfield",
}

REGIONS = {
    "1": {
        "name": "Maryland (ALL: Columbia, EC, Severn)",
        "zips": [
            "21044",
            "21045",
            "21046",  # Columbia
            "21042",
            "21043",  # Ellicott City
            "20723",  # Scaggsville
            "21144",
            "21076",
            "20794",  # Severn/Hanover/Jessup
        ],
    },
    "2": {
        "name": "Long Island (East End)",
        "zips": [
            "11901",  # Riverhead
            "11946",  # Hampton Bays
            "11968",  # Southampton
            "11976",  # Water Mill
            "11932",  # Bridgehampton
            "11937",  # East Hampton
            "11930",  # Amagansett
            "11954",  # Montauk
        ],
    },
    "3": {
        "name": "Western Mass (I-91 Corridor)",
        "zips": [
            "01103",  # Springfield
            "01020",  # Chicopee
            "01040",  # Holyoke
            "01027",  # Easthampton
            "01060",  # Northampton
            "01035",  # Hadley
            "01002",  # Amherst
            "01054",  # Leverett
            "01373",  # South Deerfield
            "01301",  # Greenfield
        ],
    },
    "4": {
        "name": "Commute: Severn <-> Scaggsville",
        "zips": [
            "21144",  # Severn (Start)
            "21076",  # Hanover
            "20794",  # Jessup (The middle gap)
            "20763",  # Savage
            "20723",  # Scaggsville (End)
        ],
    },
}

# --- 2. CONFIGURATION: LOYALTY ---
# Added "Features" and "Dallas Parkway" to block the GasBuddy HQ address
BLOCKLIST = ["BJ's", "Costco", "Sam's Club", "Features", "GasBuddy", "Dallas Parkway"]

DISCOUNTS = {
    # MD
    "Royal Farms": 0.10,
    "Giant": 0.05,
    "High's": 0.05,
    # MA / NY
    "Cumberland": 0.10,
    "Big Y": 0.05,
    "Pride": 0.10,
    "Stop & Shop": 0.10,
    # National
    "Speedway": 0.05,
    "Sheetz": 0.03,
    "7-Eleven": 0.03,
    "7-11": 0.03,
    "Shell": 0.05,
    "Exxon": 0.03,
    "Mobil": 0.03,
    "Sunoco": 0.03,
    "BP": 0.05,
    "Wawa": 0.00,
}


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
    for n in neighbors:
        if count >= 4:
            break  # Limit to +4 neighbors (5 total)
        if n["zip"] != center_zip:
            top_zips.append(n["zip"])
            count += 1

    print(f"   Targeting {len(top_zips)} key zip codes: {', '.join(top_zips)}")
    return top_zips


def get_region_choice(cli_choice=None, cli_zip=None):
    if cli_choice:
        choice = cli_choice
    else:
        print("\n--- SELECT REGION ---")
        print("1. Maryland (ALL: Columbia, EC, Severn)")
        print("2. Long Island (Riverhead - Montauk)")
        print("3. Western Mass (Springfield - Deerfield)")
        print("4. Commute Only: Severn <-> Scaggsville")
        print("5. CUSTOM SEARCH (Radius Calculation)")
        choice = input("Enter number: ").strip()

    if choice == "5":
        if cli_zip:
            center = cli_zip
        else:
            center = input("Enter Center Zip Code: ").strip()
        zips = calculate_radius_zips(center, miles=15)
        return {"name": f"Custom_Radius_{center}", "zips": zips}

    return REGIONS.get(choice, REGIONS["4"])


def clean_address(full_text):
    """
    Parses a blob of text to find the street address line.
    Filters out 'Cash/Credit' and fuel grades.
    """
    lines = re.split(r"\s{2,}|\n", full_text)
    bad_keywords = [
        "Regular",
        "Premium",
        "Diesel",
        "Midgrade",
        "UNL88",
        "Cash",
        "Credit",
        "Station Brand",
        "Payment",
    ]

    # Regex: Starts with digits, followed by words, ends with Road Type
    addr_regex = re.compile(
        r"^\d{1,5}\s+[A-Za-z0-9\.\s]+(?:Rd|St|Ave|Blvd|Ln|Dr|Hwy|Pike|Way|Cir|Ct|Pl|Bypass|Expy)",
        re.IGNORECASE,
    )

    for line in lines:
        line = line.strip()
        if any(bad in line for bad in bad_keywords):
            continue

        match = addr_regex.search(line)
        if match:
            return match.group(0)

    return "Unknown Address"


def scrape_gasbuddy(region_config, headless=False):
    print(f"\n🚀 Launching Browser ({'Headless' if headless else 'Windowed'} mode)...")
    options = Options()
    
    # Common options to avoid bot detection
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    if headless:
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
    else:
        options.add_argument("--start-maximized")
    
    driver = webdriver.Chrome(options=options)

    scraped_data = []

    try:
        for zip_code in region_config["zips"]:
            city_name = ZIP_MAP.get(zip_code, zip_code)
            print(f"\n📍 Navigating to: {city_name} ({zip_code})...")

            url = f"https://www.gasbuddy.com/home?search={zip_code}&fuel=1"
            driver.get(url)

            # --- HUMAN INTERVENTION / WAIT ---
            if not headless:
                print(f"👉 ACTION REQUIRED for {zip_code}:")
                print("   1. If Cloudflare checks you, click the box.")
                print("   2. Wait for the list of stations to appear.")
                input("   3. Press ENTER here once the prices are visible... ")
            else:
                print("   Waiting for page to load (15s)...")
                time.sleep(15)

            soup = BeautifulSoup(driver.page_source, "html.parser")

            # Parse Prices
            price_regex = re.compile(r"\$\s*([2-5]\.\d{2})")
            found_prices = soup.find_all(string=price_regex)

            print(f"   (Found {len(found_prices)} prices)")

            for price_node in found_prices:
                try:
                    base_price = float(price_regex.search(price_node).group(1))

                    # Walk up to find the "Card"
                    card = price_node.parent
                    depth = 0
                    while card and depth < 8:
                        if card.name == "div" and card.find("h3"):
                            break
                        card = card.parent
                        depth += 1

                    if not card:
                        continue

                    # Name
                    name_tag = card.find("h3")
                    name = name_tag.get_text(strip=True) if name_tag else "Unknown"
                    name = re.sub(r"\d+(\.\d+)?\s*mi.*", "", name).strip()

                    # Address Cleaning
                    full_text = card.get_text("\n", strip=True)
                    street_addr = clean_address(full_text)
                    full_address = f"{street_addr}, {zip_code}"

                    # Filter Blocklist (Checks Name AND Address now)
                    if any(b.lower() in name.lower() for b in BLOCKLIST):
                        continue
                    if any(b.lower() in full_address.lower() for b in BLOCKLIST):
                        continue

                    # Discounts
                    discount = 0.0
                    rule = "-"
                    for brand, amount in DISCOUNTS.items():
                        if brand.lower() in name.lower():
                            discount = amount
                            rule = brand
                            break

                    scraped_data.append(
                        {
                            "City": city_name,
                            "Zip": zip_code,
                            "Station": name,
                            "Address": full_address,
                            "Base": base_price,
                            "Net": round(base_price - discount, 2),
                            "Discount": rule,
                        }
                    )

                except Exception:
                    continue

    finally:
        driver.quit()

    return scraped_data


def main():
    # Check for CLI arguments
    args = sys.argv[1:]
    
    # Check for --headless flag
    is_headless_requested = "--headless" in args
    
    # Extract positional arguments (choice and zip) by ignoring flags
    pos_args = [a for a in args if not a.startswith("-")]
    
    cli_choice = pos_args[0] if len(pos_args) > 0 else None
    cli_zip = pos_args[1] if len(pos_args) > 1 else None
    
    # Detect if running in GitHub Actions or requested via CLI
    is_automated = (os.environ.get("GITHUB_ACTIONS") == "true") or is_headless_requested

    region = get_region_choice(cli_choice, cli_zip)

    # --- PRE-CHECK: Ensure history directory exists ---
    history_dir = "history"
    if not os.path.exists(history_dir):
        os.makedirs(history_dir)

    raw_name = region["name"]
    cleaned_name = raw_name.replace("/", "_").replace(" ", "_").replace(":", "")
    safe_name = re.sub(r"[^\w\-_]", "", cleaned_name)
    
    # Use Eastern Time for consistent naming
    now = datetime.datetime.now(ZoneInfo("America/New_York"))
    
    date_str = now.strftime("%Y-%m-%d_%H-%M")
    filename = os.path.join(history_dir, f"gas_{safe_name}_{date_str}.csv")

    data = scrape_gasbuddy(region, headless=is_automated)

    if not data:
        print("❌ No data found.")
        return

    df = pd.DataFrame(data)
    df = df.drop_duplicates(subset=["Station", "Address"])

    df.to_csv(filename, index=False)

    # Save a "latest" version in the root directory for easy access by external sites
    latest_filename = f"latest_{safe_name}.csv"
    df.to_csv(latest_filename, index=False)

    print("\n" + "=" * 80)
    print("✅ DATA COLLECTED")
    print("=" * 80)
    print(f"Historical File: {os.path.abspath(filename)}")
    print(f"Latest Pointer:   {os.path.abspath(latest_filename)}")

    # --- DISPLAY LOGIC ---
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


if __name__ == "__main__":
    main()
