import argparse
import re
import sys
import time
from typing import Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; cemetery-data-processor/1.0)"}
AREA_PATTERNS = [
    re.compile(r"(\d+[\d,.]*)\s*acres", re.IGNORECASE),
    re.compile(r"(\d+[\d,.]*)\s*acre", re.IGNORECASE),
    re.compile(r"(\d+[\d,.]*)\s*ha", re.IGNORECASE),
]
WIKI_PREFIX = re.compile(r"https?://en\.wikipedia\.org/wiki/", re.IGNORECASE)


def log(message: str) -> None:
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Filter cemetery checkpoint data to keep validated acreage sources "
            "with Wikipedia-derived cemetery names."
        )
    )
    parser.add_argument(
        "--input",
        default="cemetery_checkpoint2.csv",
        help="Path to the raw checkpoint CSV (default: cemetery_checkpoint2.csv)",
    )
    parser.add_argument(
        "--output",
        default="validated_cemetery_areas.csv",
        help="Where to write the cleaned and validated CSV",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.1,
        help=(
            "Allowed absolute difference (in acres) between stored acreage and "
            "area detected from the source page"
        ),
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip re-fetching area_source pages (not recommended)",
    )
    return parser.parse_args()


def extract_area(text: str) -> Optional[float]:
    for pattern in AREA_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        raw_value = match.group(1).replace(",", "")
        try:
            value = float(raw_value)
        except ValueError:
            continue
        if "ha" in pattern.pattern.lower():
            return value * 2.47105
        return value
    return None


def fetch_area_from_source(url: str) -> Optional[float]:
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text(" ", strip=True)
    return extract_area(text)


def extract_cemetery_name(url: str) -> str:
    cleaned = WIKI_PREFIX.sub("", url).strip()
    return cleaned or url


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if "area_acres" not in df.columns or "area_source" not in df.columns:
        raise ValueError("Input CSV must contain area_acres and area_source columns")

    log("Keeping area_acres and area_source columns")
    cleaned = df[["area_acres", "area_source"]].copy()

    log("Dropping rows with missing area_acres")
    cleaned["area_acres"] = pd.to_numeric(cleaned["area_acres"], errors="coerce")
    cleaned = cleaned[cleaned["area_acres"].notna()]

    log("Filtering area_source values that mention 'cemetery'")
    cleaned = cleaned[cleaned["area_source"].str.contains("cemetery", case=False, na=False)]

    log("Removing duplicate area_acres + area_source combinations")
    cleaned = cleaned.drop_duplicates(subset=["area_acres", "area_source"], keep="first")

    log("Adding cemetery_name column from area_source")
    cleaned.insert(0, "cemetery_name", cleaned["area_source"].apply(extract_cemetery_name))

    return cleaned.reset_index(drop=True)


def validate_areas(df: pd.DataFrame, tolerance: float) -> pd.DataFrame:
    validated_rows = []
    mismatches = 0
    failures = 0

    for idx, row in df.iterrows():
        source_url = row["area_source"]
        try:
            fetched_area = fetch_area_from_source(source_url)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            log(f"[{idx + 1}/{len(df)}] Failed to fetch {source_url}: {exc}")
            continue

        if fetched_area is None:
            failures += 1
            log(f"[{idx + 1}/{len(df)}] No acreage found in source {source_url}")
            continue

        stored_area = float(row["area_acres"])
        if abs(fetched_area - stored_area) <= tolerance:
            validated_rows.append(row)
            log(
                f"[{idx + 1}/{len(df)}] Validated {source_url} — stored {stored_area} acres, "
                f"found {fetched_area} acres"
            )
        else:
            mismatches += 1
            log(
                f"[{idx + 1}/{len(df)}] MISMATCH for {source_url}: stored {stored_area} acres, "
                f"found {fetched_area} acres"
            )

    log(
        f"Validation summary — kept {len(validated_rows)} rows, "
        f"mismatches: {mismatches}, failures: {failures}"
    )

    if not validated_rows:
        log("No rows passed validation; output will be empty")
        return df.iloc[0:0]

    return pd.DataFrame(validated_rows).reset_index(drop=True)


def main() -> int:
    args = parse_args()

    log(f"Loading input CSV from {args.input}")
    df = pd.read_csv(args.input)

    log("Applying cleaning steps")
    cleaned = clean_dataframe(df)

    if not args.skip_validation:
        log("Re-fetching area_source pages for validation (internet required)")
        cleaned = validate_areas(cleaned, args.tolerance)
    else:
        log("Skipping validation; output will rely on existing area_acres values")

    log(f"Writing {len(cleaned)} rows to {args.output}")
    cleaned.to_csv(args.output, index=False)
    log("Done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
