"""Original standalone Singapore scrape script (inline config, all 5 sites incl. LinkedIn).

Preserved for ad-hoc CSV export. For the portal worker, use the FastAPI sidecar instead:
  uv run uvicorn jobspy_api.main:app --port 8001
"""

import csv

import pandas as pd
from jobspy import scrape_jobs

# Broad sweep: location-only plus generic role/industry terms (not tech-specific)
SEARCH_TERMS: list[str | None] = [
    None,  # all jobs in Singapore (location-only)
    "full time",
    "part time",
    "manager",
    "executive",
    "analyst",
    "administrator",
    "assistant",
    "sales",
    "marketing",
    "finance",
    "accounting",
    "human resources",
    "operations",
    "customer service",
    "engineer",
    "technician",
    "consultant",
    "specialist",
    "coordinator",
    "intern",
    "graduate",
    "healthcare",
    "education",
    "retail",
    "logistics",
    "hospitality",
    "legal",
    "design",
]

SITE_NAMES = ["indeed", "linkedin", "glassdoor", "google", "bayt"]
LOCATION = "Singapore"
COUNTRY = "singapore"
RESULTS_WANTED = 5  # per site, per search term (boards cap around ~1000/search)
HOURS_OLD = 504  # last 3 weeks (21 days)


def google_query(term: str | None) -> str:
    label = term or "jobs"
    return f"{label} in {LOCATION} since 3 weeks"


def display_term(term: str | None) -> str:
    return term if term else "(all jobs)"


all_jobs: list[pd.DataFrame] = []

for term in SEARCH_TERMS:
    print(f"\n--- Scraping: {display_term(term)} ---")
    jobs = scrape_jobs(
        site_name=SITE_NAMES,
        search_term=term,
        google_search_term=google_query(term),
        location=LOCATION,
        country_indeed=COUNTRY,
        results_wanted=RESULTS_WANTED,
        hours_old=HOURS_OLD,
        verbose=2,
    )
    if not jobs.empty:
        jobs["search_term"] = display_term(term)
        all_jobs.append(jobs)
        print(f"  Found {len(jobs)} jobs")

if not all_jobs:
    print("No jobs found.")
else:
    combined = pd.concat(all_jobs, ignore_index=True)
    combined = combined.drop_duplicates(subset=["job_url"], keep="first")

    print(f"\nTotal: {len(combined)} unique jobs (from {sum(len(df) for df in all_jobs)} raw)")
    print(combined[["site", "search_term", "title", "company", "location"]].head(10))

    combined.to_csv(
        "sg_jobs.csv",
        quoting=csv.QUOTE_NONNUMERIC,
        escapechar="\\",
        index=False,
    )
    print("Saved to sg_jobs.csv")
