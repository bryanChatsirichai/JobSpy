"""Job search routes — one page maps to one search-term sweep."""

from __future__ import annotations

import asyncio
import logging

import numpy as np
import pandas as pd
from fastapi import APIRouter, Query
from jobspy import scrape_jobs

from jobspy_api import config

logger = logging.getLogger(__name__)

router = APIRouter()


def _scrape_term(
    term: str | None,
    *,
    results_wanted: int,
    hours_old: int,
) -> list[dict]:
    """Run scrape_jobs for a single search term (blocking)."""
    label = config.display_term(term)
    logger.info("Scraping search term: %s", label)

    df = scrape_jobs(
        site_name=config.SITE_NAMES,
        search_term=term,
        google_search_term=config.google_query(term),
        location=config.LOCATION,
        country_indeed=config.COUNTRY,
        results_wanted=results_wanted,
        hours_old=hours_old,
        verbose=1,
    )

    if df.empty:
        logger.info("No jobs for term: %s", label)
        return []

    df = df.drop_duplicates(subset=["job_url"], keep="first")
    df["search_term"] = label
    records = df.replace({np.nan: None}).to_dict(orient="records")

    for record in records:
        if record.get("date_posted") is not None:
            record["date_posted"] = str(record["date_posted"])

    logger.info("Term %s returned %s jobs", label, len(records))
    return records


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/jobs/search")
async def search_jobs(
    page: int = Query(0, ge=0, description="0-based search term index"),
) -> dict:
    total_terms = len(config.SEARCH_TERMS)
    if page >= total_terms:
        return {
            "success": True,
            "page": page,
            "search_term": None,
            "total_terms": total_terms,
            "has_more": False,
            "jobs": [],
        }

    term = config.SEARCH_TERMS[page]

    try:
        jobs = await asyncio.to_thread(
            _scrape_term,
            term,
            results_wanted=config.RESULTS_WANTED,
            hours_old=config.HOURS_OLD,
        )
    except Exception:
        logger.exception("Scrape failed for page=%s term=%s", page, config.display_term(term))
        return {
            "success": False,
            "page": page,
            "search_term": config.display_term(term),
            "total_terms": total_terms,
            "has_more": page + 1 < total_terms,
            "jobs": [],
        }

    return {
        "success": True,
        "page": page,
        "search_term": config.display_term(term),
        "total_terms": total_terms,
        "has_more": page + 1 < total_terms,
        "jobs": jobs,
    }
