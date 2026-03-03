# Gemini Project Directives

This document contains foundational mandates for the Gemini agent working in this repository. These rules take precedence over general heuristics.

## Gas Station Parsing Heuristic

The HTML parsing logic for extracting gas station data from GasBuddy is brittle and must adhere to the following structure. This is the single source of truth and should not be changed without explicit user direction.

1.  **Primary Container:** All station information (name, address, price) is contained within a `div` element that has a CSS class starting with `GenericStationListItem-module__station`. The parser must *first* locate these top-level containers.

2.  **Data Extraction (Children of Primary Container):**
    *   **Station Name:** The name is located within an `<h3>` tag.
    *   **Address:** The address is within an element that has a class name starting with `StationDisplay-module__address`.
    *   **Price:** The price is within an element that has a class name starting with `StationDisplayPrice-module__price`.

The parsing functions, specifically `get_station_cards` and `parse_station_card` in `src/gas_scraper/parser.py`, must be implemented using this container-based approach.
