"""Environment-driven scrape configuration shared by the API and scrape_sg.py.

Loads ``JobSpy/.env`` automatically (see ``.env.example``).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")
# Broad sweep: location-only plus generic role/industry terms (not tech-specific)
DEFAULT_SEARCH_TERMS: list[str | None] = [
    None,
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


def _parse_search_terms(raw: str) -> list[str | None]:
    """Parse JOBSPY_SEARCH_TERMS JSON array; empty strings become None."""
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        raise ValueError("JOBSPY_SEARCH_TERMS must be a JSON array")
    terms: list[str | None] = []
    for item in parsed:
        if item is None:
            terms.append(None)
        elif isinstance(item, str):
            terms.append(item or None)
        else:
            raise ValueError("JOBSPY_SEARCH_TERMS items must be strings or null")
    return terms


def _parse_site_names(raw: str) -> list[str]:
    return [site.strip() for site in raw.split(",") if site.strip()]


SITE_NAMES: list[str] = _parse_site_names(
    os.getenv("JOBSPY_SITE_NAMES", "indeed,linkedin,glassdoor,google,bayt")
)
LOCATION: str = os.getenv("JOBSPY_LOCATION", "Singapore")
COUNTRY: str = os.getenv("JOBSPY_COUNTRY", "singapore")
RESULTS_WANTED: int = int(os.getenv("JOBSPY_RESULTS_WANTED", "5"))
HOURS_OLD: int = int(os.getenv("JOBSPY_HOURS_OLD", "504"))
PORT: int = int(os.getenv("JOBSPY_PORT", "8001"))

_search_terms_env = os.getenv("JOBSPY_SEARCH_TERMS")
SEARCH_TERMS: list[str | None] = (
    _parse_search_terms(_search_terms_env) if _search_terms_env else DEFAULT_SEARCH_TERMS
)


def google_query(term: str | None) -> str:
    label = term or "jobs"
    return f"{label} in {LOCATION} since 3 weeks"


def display_term(term: str | None) -> str:
    return term if term else "(all jobs)"
