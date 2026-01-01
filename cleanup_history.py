import os
import re
from collections import defaultdict

HISTORY_DIR = "history"

def cleanup():
    """
    Scans the history directory and removes redundant files.
    Policy: Keep only the latest file (by timestamp) for each Location + Date pair.
    """
    if not os.path.exists(HISTORY_DIR):
        print(f"Directory '{HISTORY_DIR}' does not exist. Nothing to clean.")
        return

    # Regex to parse: gas_{Location}_{YYYY-MM-DD}_{HH-MM}.csv
    # We anchor to the end to safely capture the date and time.
    # Group 1: Location Name
    # Group 2: Date (YYYY-MM-DD)
    # Group 3: Time (HH-MM)
    pattern = re.compile(r"^gas_(.+)_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2})\.csv$")

    files = [f for f in os.listdir(HISTORY_DIR) if f.endswith(".csv")]
    print(f"Scanning {len(files)} CSV files in '{HISTORY_DIR}'...")

    # Dictionary to group files:
    # Key: (Location, Date)
    # Value: List of (Time_String, Filename)
    groups = defaultdict(list)

    for filename in files:
        match = pattern.match(filename)
        if match:
            location = match.group(1)
            date_str = match.group(2)
            time_str = match.group(3)
            
            key = (location, date_str)
            groups[key].append((time_str, filename))

    deleted_count = 0
    
    # Iterate over each group
    for (loc, date), file_list in groups.items():
        # If there's more than one file for this location/date, we need to clean up
        if len(file_list) > 1:
            # Sort by time string descending (latest first).
            # HH-MM format sorts correctly lexicographically.
            file_list.sort(key=lambda x: x[0], reverse=True)

            # Keep the first one (latest)
            latest_time, latest_file = file_list[0]
            
            # Remove the rest
            files_to_remove = file_list[1:]
            
            print(f"[{date}] {loc}: Keeping latest '{latest_time}' ({latest_file})")

            for _, fname in files_to_remove:
                full_path = os.path.join(HISTORY_DIR, fname)
                try:
                    os.remove(full_path)
                    print(f"  - Deleted: {fname}")
                    deleted_count += 1
                except OSError as e:
                    print(f"  - Error deleting {fname}: {e}")

    print("-" * 40)
    print(f"Cleanup complete. Deleted {deleted_count} files.")
    print("-" * 40)

if __name__ == "__main__":
    cleanup()
