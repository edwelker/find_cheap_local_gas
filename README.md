# Gas Price Tracker

I drive a lot between Maryland, Long Island, and Western Massachusetts. I noticed that gas prices can vary by 50 cents or more just a few miles apart.

I built this tool because I wanted to save money, but I also had a specific question: **Is it worth signing up for local loyalty cards?** I used AI (Gemini) to help me understand the various reward structures, and I wanted to know if the 10-cent discount at a brand name station actually made it cheaper than the generic station down the road.

### The Solution
I used Python to automate the research.

1.  **It's Targeted:** It checks specific zip codes along my commute and where my sisters and friends live.
2.  **It's Smart:** It calculates the *net* price. I used AI to research the specific discounts for various loyalty programs, so the script automatically subtracts those amounts to compare the real cost.
3.  **It's Automated:** I set up a GitHub Action to run a headless browser in the cloud twice a day. It scrapes the data, cleans it up, and saves a report.

### Sharing the Wealth
Since I track prices in Western Mass for my sisters and in Maryland for my friends, this isn't just for me. It helps them save money too.

### How it Works
*   **Python & Selenium:** Scrapes current prices from the web.
*   **GitHub Actions:** Runs the script automatically every morning and evening.
*   **Astro 5 Integration:** The raw data (CSVs) generated here acts as a datasource for a static Astro 5 website. This means I can pull up a fast, clean interface on my phone to check prices anywhere, even if the underlying scraper logic is static.

### Why this matters
This project shows how I approach problems: I saw a repetitive task (checking gas prices), I questioned the variables (loyalty cards), and I built a reliable, automated system to give me the answer.
