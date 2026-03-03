# Gemini Project Directives

This document contains foundational mandates for the Gemini agent working in this repository. These rules take precedence over general heuristics.

## Gas Station Parsing Heuristic

The HTML parsing logic for extracting gas station data from GasBuddy must follow a specific hierarchical approach. This is the single source of truth.

1.  **Find Primary Containers:** The top-level function (`get_station_cards`) must first find all potential station containers. A container is a `div` element whose `class` attribute **contains** `GenericStationListItem-module__station`.

2.  **Parse Each Container:** For each container found, the parsing function (`parse_station_card`) must search for the following **descendant** elements *within that container only*. If any of these are not found, the container should be considered invalid and skipped. Use the robust `//text()` approach to extract all text content from within the target element.
    *   **Station Name:** The name is located within a descendant `<h3>` tag. The precise path is: `.//h3[contains(@class, 'StationDisplay-module__stationName')]//text()`
    *   **Address:** The address is within a descendant `div`. The precise path is: `.//div[contains(@class, 'StationDisplay-module__address')]//text()`
    *   **Price:** The price is within a descendant `span`. The precise path is: `.//span[contains(@class, 'StationDisplayPrice-module__price')]//text()`

## Logging Requirements

-   **URL Logging:** The scraper must always output the URL being tested for each zip code. This allows for easy double-checking and debugging of the live scraping process.
