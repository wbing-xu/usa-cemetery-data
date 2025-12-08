import argparse
import csv
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from typing import Iterable, List, Optional, Set, Tuple

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://peoplelegacy.com/cemeteries/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; data-request-script/1.0)"}


def log(message: str) -> None:
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def get_soup(url: str) -> BeautifulSoup:
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def extract_state_links() -> List[str]:
    """Return absolute URLs for each state on the directory page.

    The PeopleLegacy directory lists states as links under the base cemeteries
    page. This selector may need to be adjusted if the site changes; the
    function currently collects any anchor whose href starts with the base
    cemeteries path and ends with a trailing slash.
    """

    log("Fetching state directory page...")
    soup = get_soup(BASE_URL)
    links = []
    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "")
        if not href.startswith("/cemeteries/"):
            continue
        if href.rstrip("/") == "/cemeteries":
            continue
        # Only keep state-level links (they typically have two path segments).
        if href.count("/") > 3:
            continue
        links.append(requests.compat.urljoin(BASE_URL, href))
    # Remove duplicates while preserving order.
    seen = set()
    unique_links = []
    for link in links:
        if link in seen:
            continue
        seen.add(link)
        unique_links.append(link)
    return unique_links


@dataclass
class CemeteryRecord:
    state: str
    city: str
    name: str
    area_acres: Optional[float]
    source: Optional[str]
    url: str


AREA_PATTERNS = [
    re.compile(r"(\d+[\d,.]*)\s*acres", re.IGNORECASE),
    re.compile(r"(\d+[\d,.]*)\s*acre", re.IGNORECASE),
    re.compile(r"(\d+[\d,.]*)\s*ha", re.IGNORECASE),
]

CHECKPOINT_FIELDS = ["state", "city", "name", "area_acres", "source", "url"]


def extract_area(text: str) -> Optional[float]:
    for pattern in AREA_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        raw = match.group(1).replace(",", "")
        try:
            value = float(raw)
        except ValueError:
            continue
        if "ha" in pattern.pattern.lower():
            return value * 2.47105  # hectares to acres
        return value
    return None


def search_wikipedia_area(query: str) -> tuple[Optional[float], Optional[str]]:
    params = {
        "action": "query",
        "list": "search",
        "format": "json",
        "srsearch": query,
        "srlimit": 1,
    }
    search_response = requests.get(
        "https://en.wikipedia.org/w/api.php", params=params, headers=HEADERS, timeout=30
    )
    search_response.raise_for_status()
    data = search_response.json()
    if not data.get("query", {}).get("search"):
        return None, None
    page_title = data["query"]["search"][0]["title"]

    page_response = requests.get(
        "https://en.wikipedia.org/w/api.php",
        params={
            "action": "query",
            "prop": "extracts",
            "exintro": 1,
            "explaintext": 1,
            "titles": page_title,
            "format": "json",
        },
        headers=HEADERS,
        timeout=30,
    )
    page_response.raise_for_status()
    page_data = page_response.json()
    pages = page_data.get("query", {}).get("pages", {})
    if not pages:
        return None, None
    page = next(iter(pages.values()))
    extract = page.get("extract", "")
    area = extract_area(extract)
    page_url = f"https://en.wikipedia.org/wiki/{page_title.replace(' ', '_')}"
    return area, page_url if area is not None else None


def parse_cemetery_list(state_url: str) -> Iterable[tuple[str, str, str, str]]:
    """Yield (state, city, name, cemetery_url) entries for a state.

    PeopleLegacy lists cemeteries by city inside the state page. The
    implementation collects cemetery anchors whose href contains the state slug
    to avoid pulling unrelated links.
    """

    soup = get_soup(state_url)
    state_slug = state_url.rstrip("/").split("/")[-1]
    state_name = soup.find("h1").get_text(strip=True) if soup.find("h1") else state_slug
    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "")
        if state_slug not in href:
            continue
        if "/cemetery/" not in href and "/cemeteries/" not in href:
            continue
        name = anchor.get_text(strip=True)
        if not name:
            continue
        url = requests.compat.urljoin(state_url, href)
        city = anchor.find_parent("li").find_previous("h2").get_text(strip=True) if anchor.find_parent("li") else ""
        yield state_name, city, name, url


def load_checkpoint(path: str) -> Tuple[List[CemeteryRecord], Set[str]]:
    records: List[CemeteryRecord] = []
    processed: Set[str] = set()
    if not path or not os.path.exists(path):
        return records, processed
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            url = row.get("url") or ""
            processed.add(url)
            area_raw = row.get("area_acres") or ""
            area_value = None
            try:
                area_value = float(area_raw) if area_raw else None
            except ValueError:
                area_value = None
            records.append(
                CemeteryRecord(
                    state=row.get("state", ""),
                    city=row.get("city", ""),
                    name=row.get("name", ""),
                    area_acres=area_value,
                    source=row.get("source") or None,
                    url=url,
                )
            )
    log(f"Loaded {len(records)} existing records from checkpoint {path}")
    return records, processed


def append_checkpoint(record: CemeteryRecord, path: str) -> None:
    exists = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CHECKPOINT_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow({
            "state": record.state,
            "city": record.city,
            "name": record.name,
            "area_acres": record.area_acres if record.area_acres is not None else "",
            "source": record.source or "",
            "url": record.url,
        })
    log(f"    • checkpoint saved to {path}")


def write_live_preview(records: List[CemeteryRecord], path: str) -> None:
    """Persist an always-up-to-date CSV so users can inspect progress mid-run."""

    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CHECKPOINT_FIELDS)
        writer.writeheader()
        for record in records:
            writer.writerow({
                "state": record.state,
                "city": record.city,
                "name": record.name,
                "area_acres": record.area_acres if record.area_acres is not None else "",
                "source": record.source or "",
                "url": record.url,
            })
    log(f"    • live preview updated at {path}")


def crawl_cemetery_areas(
    limit_states: Optional[int] = None,
    delay: float = 0.5,
    records: Optional[List[CemeteryRecord]] = None,
    processed_urls: Optional[Set[str]] = None,
    checkpoint_path: Optional[str] = None,
    live_preview_path: Optional[str] = None,
) -> List[CemeteryRecord]:
    records = records or []
    processed_urls = processed_urls or set()
    state_links = extract_state_links()
    total_states = len(state_links)
    log(f"Found {total_states} state links. Starting crawl...")
    total_cemeteries = len(processed_urls)
    total_with_area = len([r for r in records if r.area_acres is not None])
    for idx, state_link in enumerate(state_links):
        if limit_states is not None and idx >= limit_states:
            break
        log(f"[{idx + 1}/{total_states}] Crawling {state_link} ...")
        state_cemeteries = 0
        state_with_area = 0
        for count, (state, city, name, url) in enumerate(parse_cemetery_list(state_link), start=1):
            if url in processed_urls:
                log(f"  - ({count}) {name} ({city}, {state}) already processed — skipping")
                continue
            state_cemeteries += 1
            total_cemeteries += 1
            log(f"  - ({count}) {name} ({city}, {state}) -> searching area")
            area, source = search_wikipedia_area(f"{name} {city} {state} cemetery area")
            if area is not None:
                state_with_area += 1
                total_with_area += 1
                log(f"    • area found: {area:.2f} acres")
            else:
                log("    • no area found")
            record = CemeteryRecord(
                state=state, city=city, name=name, area_acres=area, source=source, url=url
            )
            records.append(record)
            processed_urls.add(url)
            if checkpoint_path:
                append_checkpoint(record, checkpoint_path)
            if live_preview_path:
                write_live_preview(records, live_preview_path)
            time.sleep(delay)
        log(
            f"Finished state {state_link} — processed {state_cemeteries} cemeteries, "
            f"found areas for {state_with_area}"
        )
    log(
        f"Crawl complete. Cemeteries processed: {total_cemeteries}. "
        f"Areas found: {total_with_area}. Missing areas: {total_cemeteries - total_with_area}."
    )
    return records


def build_normal_distribution_table(areas: List[float], bins: int = 10) -> pd.DataFrame:
    if not areas:
        return pd.DataFrame(columns=["bin_start_acres", "bin_end_acres", "count", "share"])
    series = pd.Series(areas)
    counts, bin_edges = np.histogram(series, bins=bins)
    total = counts.sum()
    rows = []
    for start, end, count in zip(bin_edges[:-1], bin_edges[1:], counts):
        rows.append(
            {
                "bin_start_acres": start,
                "bin_end_acres": end,
                "count": int(count),
                "share": float(count) / total if total else 0.0,
            }
        )
    return pd.DataFrame(rows)


def export_to_excel(records: List[CemeteryRecord], path: str) -> None:
    df = pd.DataFrame([asdict(r) for r in records if r.area_acres is not None])
    if df.empty:
        export_df = pd.DataFrame(columns=["state", "city", "name", "area_acres", "source"])
        distribution = pd.DataFrame()
    else:
        export_df = df[["state", "city", "name", "area_acres", "source"]]
        distribution = build_normal_distribution_table(export_df["area_acres"].tolist())
    log(
        f"Writing {len(export_df)} cemeteries with acreage to {path} "
        f"(distribution rows: {len(distribution)})"
    )
    with pd.ExcelWriter(path) as writer:
        export_df.to_excel(writer, sheet_name="cemeteries", index=False)
        distribution.to_excel(writer, sheet_name="area_distribution", index=False)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crawl PeopleLegacy and fetch cemetery acreage from Wikipedia.")
    parser.add_argument("--output", default="cemetery_areas.xlsx", help="Path for the output Excel file.")
    parser.add_argument(
        "--limit-states",
        type=int,
        default=None,
        help="Limit how many state pages to crawl (useful for quick tests).",
    )
    parser.add_argument(
        "--delay", type=float, default=0.5, help="Seconds to sleep between Wikipedia requests to be polite."
    )
    parser.add_argument(
        "--checkpoint",
        default="cemetery_checkpoint.csv",
        help="CSV file used to save progress while crawling (also used to resume).",
    )
    parser.add_argument(
        "--no-checkpoint",
        action="store_true",
        help="Disable writing checkpoint CSVs (progress cannot be resumed).",
    )
    parser.add_argument(
        "--live-preview",
        default=None,
        help=(
            "Path to a CSV that is rewritten after each cemetery so you can open "
            "it while the crawl runs to view current results."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    checkpoint_path = None if args.no_checkpoint else args.checkpoint
    records: List[CemeteryRecord]
    processed_urls: Set[str]
    if checkpoint_path:
        records, processed_urls = load_checkpoint(checkpoint_path)
    else:
        records, processed_urls = [], set()
    start = time.time()
    log(
        "Starting crawl. This requires internet access and may take time... "
        "Watch the log messages for progress."
    )
    try:
        crawl_cemetery_areas(
            limit_states=args.limit_states,
            delay=args.delay,
            records=records,
            processed_urls=processed_urls,
            checkpoint_path=checkpoint_path,
            live_preview_path=args.live_preview,
        )
    except KeyboardInterrupt:
        log("Interrupted by user — exporting partial progress from checkpoint and memory.")
    except Exception as exc:
        log(f"Error encountered: {exc}. Writing partial output before exiting.")
        raise
    finally:
        export_to_excel(records, args.output)
        duration = time.time() - start
        log(f"Finished in {duration:.1f} seconds. Output written to {args.output}")


if __name__ == "__main__":
    main(sys.argv[1:])
