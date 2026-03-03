import os
import re
from collections import defaultdict
from loguru import logger

HISTORY_DIR = "history"


def cleanup():
    """
    Scans the history directory and removes redundant files.
    Policy: Keep only the latest file (by timestamp) for each Location + Date pair.
    """
    if not os.path.exists(HISTORY_DIR):
        logger.warning(f"Directory '{HISTORY_DIR}' does not exist. Nothing to clean.")
        return

    # Regex to parse: gas_{Location}_{YYYY-MM-DD}_{HH-MM}.csv
    pattern = re.compile(r"^gas_(.+)_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2})\.csv$")

    files = [f for f in os.listdir(HISTORY_DIR) if f.endswith(".csv")]
    logger.info(f"Scanning {len(files)} CSV files in '{HISTORY_DIR}'...")

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

    for (loc, date), file_list in groups.items():
        if len(file_list) > 1:
            file_list.sort(key=lambda x: x[0], reverse=True)
            latest_time, latest_file = file_list[0]
            files_to_remove = file_list[1:]

            logger.info(
                f"[{date}] {loc}: Keeping latest '{latest_time}' ({latest_file})"
            )

            for _, fname in files_to_remove:
                full_path = os.path.join(HISTORY_DIR, fname)
                try:
                    os.remove(full_path)
                    logger.info(f"  - Deleted: {fname}")
                    deleted_count += 1
                except OSError as e:
                    logger.error(f"  - Error deleting {fname}: {e}")

    logger.info(f"Cleanup complete. Deleted {deleted_count} files.")


if __name__ == "__main__":
    cleanup()
