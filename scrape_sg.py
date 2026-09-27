"""Scrape Singapore jobs to CSV using shared config (aligned with jobspy_api sidecar).

Run:
  uv run python scrape_sg.py
  uv run python scrape_sg.py --output my_jobs.csv

Original inline script preserved as scrape_sg_original.py.
"""

from __future__ import annotations

import argparse
import csv
import sys

import pandas as pd
from jobspy import scrape_jobs

from jobspy_api.config import (
    COUNTRY,
    HOURS_OLD,
    LOCATION,
    RESULTS_WANTED,
    SEARCH_TERMS,
    SITE_NAMES,
    display_term,
    google_query,
)

DEFAULT_OUTPUT = "sg_jobs.csv"


def scrape_all_terms(*, results_wanted: int, hours_old: int) -> pd.DataFrame:
    """Run scrape_jobs for every configured search term and return deduped jobs."""
    frames: list[pd.DataFrame] = []

    for term in SEARCH_TERMS:
        label = display_term(term)
        print(f"\n--- Scraping: {label} ---")
        jobs = scrape_jobs(
            site_name=SITE_NAMES,
            search_term=term,
            google_search_term=google_query(term),
            location=LOCATION,
            country_indeed=COUNTRY,
            results_wanted=results_wanted,
            hours_old=hours_old,
            verbose=2,
        )
        if jobs.empty:
            print("  Found 0 jobs")
            continue

        jobs["search_term"] = label
        frames.append(jobs)
        print(f"  Found {len(jobs)} jobs")

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    return combined.drop_duplicates(subset=["job_url"], keep="first")


def save_csv(df: pd.DataFrame, path: str) -> None:
    df.to_csv(
        path,
        quoting=csv.QUOTE_NONNUMERIC,
        escapechar="\\",
        index=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape Singapore jobs to CSV via JobSpy")
    parser.add_argument(
        "--output",
        "-o",
        default=DEFAULT_OUTPUT,
        help=f"Output CSV path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--results-wanted",
        type=int,
        default=RESULTS_WANTED,
        help=f"Jobs per site per term (default: {RESULTS_WANTED})",
    )
    parser.add_argument(
        "--hours-old",
        type=int,
        default=HOURS_OLD,
        help=f"Max job age in hours (default: {HOURS_OLD})",
    )
    args = parser.parse_args()

    print(f"Sites: {', '.join(SITE_NAMES)}")
    print(f"Location: {LOCATION} | Terms: {len(SEARCH_TERMS)}")

    combined = scrape_all_terms(
        results_wanted=args.results_wanted,
        hours_old=args.hours_old,
    )

    if combined.empty:
        print("No jobs found.")
        return 1

    raw_total = len(combined)
    print(f"\nTotal: {raw_total} unique jobs")
    print(combined[["site", "search_term", "title", "company", "location"]].head(10))

    save_csv(combined, args.output)
    print(f"Saved to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
