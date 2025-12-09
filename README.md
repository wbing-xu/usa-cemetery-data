# USA Cemetery Data Helper

This repository provides a helper script to crawl public cemetery listings on PeopleLegacy, look up available acreage information from Wikipedia, and export the results to Excel. The crawl collects cemeteries by state, walks into each city's page to reach every individual cemetery listing, attempts to find acreage information for each cemetery, and builds a second sheet with a histogram-style normal distribution table.

## Usage

1. Install dependencies:

```bash
pip install -r requirements.txt
```

> If you see an error mentioning `openpyxl` when writing Excel files, double-check that
> `pip install -r requirements.txt` completed successfully.

2. Run the crawler (internet access required). During the run you will see timestamped progress printed for each state and cemetery, plus a summary when the crawl completes. Progress is continually written to `cemetery_checkpoint.csv` so you can resume if the process stops unexpectedly. If you want to watch results accumulate in real time, add the `--live-preview` flag to keep a separate CSV updated after every cemetery. Area lookups now run in parallel worker threads so you can increase speed with `--max-workers` while keeping PeopleLegacy fetches politely throttled with jittered delays:

```bash
# Full crawl (faster lookups with default checkpointing and jittered throttling):
python scrape_cemeteries.py

# Quick smoke test for 1 state (prints progress to the terminal):
python scrape_cemeteries.py --limit-states 1 --output test.xlsx --max-workers 8

# Resume from a previous checkpoint file (created automatically unless disabled):
python scrape_cemeteries.py --output resumed.xlsx --checkpoint cemetery_checkpoint.csv

# Watch data collect live in another CSV while still writing checkpoints:
python scrape_cemeteries.py --live-preview live_progress.csv

# Disable checkpoint writing if you want a one-off run:
python scrape_cemeteries.py --no-checkpoint

# Speed up (while staying polite) by parallelizing Wikipedia lookups and adjusting jitter:
python scrape_cemeteries.py --max-workers 12 --delay 0.2 --delay-jitter 0.1 --peoplelegacy-delay 0.5 --peoplelegacy-jitter 0.4
```

The script writes `cemetery_areas.xlsx` with two sheets:

- `cemeteries`: state, city, cemetery name, acreage, and the Wikipedia page (or other page) that specifically contained the acreage figure.
- `area_distribution`: binned acreage counts and relative shares to help visualize the acreage distribution.

Checkpoint and live-preview CSVs keep two separate link columns so you can validate data after interruptions:

- `area_source`: the page that provided the acreage value (saved only when an area is found). The crawler only accepts acreage values that appear in an "Area" infobox row or alongside acreage-related wording on the page so the saved link can be re-checked for accuracy.
- `cemetery_url`: the original PeopleLegacy listing used to find the cemetery (the scraper now follows the state page into each city page and finally into the cemetery detail page, so this link points at the individual cemetery, not just the city listing).

> **Note:** The scraper relies on the current HTML structure of https://peoplelegacy.com/cemeteries/. If the site changes, you may need to adjust the CSS selectors inside `scrape_cemeteries.py`. Wikipedia searches may not return acreage for every cemetery; rows without acreage are skipped from the distribution calculation.

You will know the script is still running when you see timestamped lines such as:

```
[12:00:00] Starting crawl. This requires internet access and may take time... Watch the log messages for progress.
[12:00:02] [1/51] Crawling https://peoplelegacy.com/cemeteries/alabama/ ...
[12:00:05]   - (3) Memorial Gardens (Example City, Alabama) -> queueing area lookup
[12:00:06]     • area found for Memorial Gardens: 12.50 acres
...
[12:05:30] Finished state https://peoplelegacy.com/cemeteries/alabama/ — processed 120 cemeteries, found areas for 17
[12:05:30] Crawl complete. Cemeteries processed: 120. Areas found: 17. Missing areas: 103.
[12:05:30] Finished in 330.5 seconds. Output written to cemetery_areas.xlsx
```

If you do not see any output:

- Ensure you are running with internet access (PeopleLegacy and Wikipedia are both required).
- Try the smoke-test command above to verify progress logging.
- Some requests may take up to 30 seconds because of the HTTP timeout; allow the crawl to finish or adjust the `--delay` flag if you need faster runs. Automatic retries with backoff are enabled for transient errors (429/5xx). When Wikipedia or PeopleLegacy pages fail to load, the error is logged and the crawler continues to the next cemetery instead of stopping the run.
- If PeopleLegacy returns “Too Many Requests” (429) messages, re-run with a higher `--peoplelegacy-delay` (default is 0.5 seconds with added jitter) so the scraper sleeps between PeopleLegacy page fetches. The crawler will also honor `Retry-After` headers and back off before retrying. Pairing small delays with jitter helps avoid anti-scraping throttles while still keeping the run fast.
- If you interrupt the crawl (Ctrl+C), the script will still export whatever was collected to both the Excel file and the checkpoint CSV. Re-run with the same `--checkpoint` path to continue where you left off.

## Cleaning an existing checkpoint

If you already have a `cemetery_checkpoint2.csv` file and want to keep only verified acreage rows (without touching `scrape_cemeteries.py`):

```bash
# Produces validated_cemetery_areas.csv with columns: cemetery_name, area_acres, area_source
python process_checkpoint.py --input cemetery_checkpoint2.csv --output validated_cemetery_areas.csv
```

The cleaning script performs the requested steps automatically:

- Keeps only `area_acres` and `area_source`, drops rows without acreage, and filters sources that mention "cemetery" (case-insensitive).
- Removes duplicate `(area_acres, area_source)` combinations.
- Adds a leading `cemetery_name` column by stripping `https://en.wikipedia.org/wiki/` from each `area_source` URL.
- Re-fetches every `area_source` page to confirm the acreage still matches the stored `area_acres` (default tolerance ±0.1 acres). Rows that fail to match are excluded, and failures are reported in the log.

> Use `--skip-validation` if you need to run without internet access, but the output will not be cross-checked against the source pages.

## Environment limitations

This repository was authored in an offline environment, so the crawler could not be executed or validated here. Ensure you run it with network access and review the results for accuracy.
