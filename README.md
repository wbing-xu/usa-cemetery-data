# USA Cemetery Data Helper

This repository provides a helper script to crawl public cemetery listings on PeopleLegacy, look up available acreage information from Wikipedia, and export the results to Excel. The crawl collects cemeteries by state, attempts to find acreage information for each cemetery, and builds a second sheet with a histogram-style normal distribution table.

## Usage

1. Install dependencies:

```bash
pip install -r requirements.txt
```

> If you see an error mentioning `openpyxl` when writing Excel files, double-check that
> `pip install -r requirements.txt` completed successfully.

2. Run the crawler (internet access required). During the run you will see timestamped progress printed for each state and cemetery, plus a summary when the crawl completes. Progress is continually written to `cemetery_checkpoint.csv` so you can resume if the process stops unexpectedly. If you want to watch results accumulate in real time, add the `--live-preview` flag to keep a separate CSV updated after every cemetery:

```bash
# Full crawl (slow) with default checkpointing:
python scrape_cemeteries.py

# Quick smoke test for 1 state (prints progress to the terminal):
python scrape_cemeteries.py --limit-states 1 --output test.xlsx

# Resume from a previous checkpoint file (created automatically unless disabled):
python scrape_cemeteries.py --output resumed.xlsx --checkpoint cemetery_checkpoint.csv

# Watch data collect live in another CSV while still writing checkpoints:
python scrape_cemeteries.py --live-preview live_progress.csv

# Disable checkpoint writing if you want a one-off run:
python scrape_cemeteries.py --no-checkpoint
```

The script writes `cemetery_areas.xlsx` with two sheets:

- `cemeteries`: state, city, cemetery name, acreage, and the Wikipedia page that supplied the area.
- `area_distribution`: binned acreage counts and relative shares to help visualize the acreage distribution.

> **Note:** The scraper relies on the current HTML structure of https://peoplelegacy.com/cemeteries/. If the site changes, you may need to adjust the CSS selectors inside `scrape_cemeteries.py`. Wikipedia searches may not return acreage for every cemetery; rows without acreage are skipped from the distribution calculation.

You will know the script is still running when you see timestamped lines such as:

```
[12:00:00] Starting crawl. This requires internet access and may take time... Watch the log messages for progress.
[12:00:02] [1/51] Crawling https://peoplelegacy.com/cemeteries/alabama/ ...
[12:00:05]   - (3) Memorial Gardens (Example City, Alabama) -> searching area
[12:00:06]     • area found: 12.50 acres
...
[12:05:30] Finished state https://peoplelegacy.com/cemeteries/alabama/ — processed 120 cemeteries, found areas for 17
[12:05:30] Crawl complete. Cemeteries processed: 120. Areas found: 17. Missing areas: 103.
[12:05:30] Finished in 330.5 seconds. Output written to cemetery_areas.xlsx
```

If you do not see any output:

- Ensure you are running with internet access (PeopleLegacy and Wikipedia are both required).
- Try the smoke-test command above to verify progress logging.
- Some requests may take up to 30 seconds because of the HTTP timeout; allow the crawl to finish or adjust the `--delay` flag if you need faster runs.
- If you interrupt the crawl (Ctrl+C), the script will still export whatever was collected to both the Excel file and the checkpoint CSV. Re-run with the same `--checkpoint` path to continue where you left off.

## Environment limitations

This repository was authored in an offline environment, so the crawler could not be executed or validated here. Ensure you run it with network access and review the results for accuracy.
