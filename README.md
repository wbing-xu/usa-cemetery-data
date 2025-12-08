# USA Cemetery Data Helper

This repository provides a helper script to crawl public cemetery listings on PeopleLegacy, look up available acreage information from Wikipedia, and export the results to Excel. The crawl collects cemeteries by state, attempts to find acreage information for each cemetery, and builds a second sheet with a histogram-style normal distribution table.

## Usage

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Run the crawler (internet access required):

```bash
python scrape_cemeteries.py
```

The script writes `cemetery_areas.xlsx` with two sheets:

- `cemeteries`: state, city, cemetery name, acreage, and the Wikipedia page that supplied the area.
- `area_distribution`: binned acreage counts and relative shares to help visualize the acreage distribution.

> **Note:** The scraper relies on the current HTML structure of https://peoplelegacy.com/cemeteries/. If the site changes, you may need to adjust the CSS selectors inside `scrape_cemeteries.py`. Wikipedia searches may not return acreage for every cemetery; rows without acreage are skipped from the distribution calculation.

## Environment limitations

This repository was authored in an offline environment, so the crawler could not be executed or validated here. Ensure you run it with network access and review the results for accuracy.
