import logging
from typing import Any

import httpx

from models import JobListing

JOBTECH_SEARCH_URL = "https://jobsearch.api.jobtechdev.se/search"
JOBTECH_AD_URL = "https://arbetsformedlingen.se/platsbanken/annonser/{ad_id}"

logger = logging.getLogger(__name__)


def get_nested(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data

    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)

    return current


def clean_text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def build_location(hit: dict[str, Any]) -> str:
    municipality = clean_text(get_nested(
        hit, "workplace_address", "municipality"))
    region = clean_text(get_nested(hit, "workplace_address", "region"))
    country = clean_text(get_nested(hit, "workplace_address", "country"))

    parts = [part for part in [municipality, region, country] if part]
    return ", ".join(parts)


def build_description(hit: dict[str, Any]) -> str:
    description = clean_text(get_nested(hit, "description", "text"))
    if description:
        return description

    text_formatted = clean_text(get_nested(
        hit, "description", "text_formatted"))
    if text_formatted:
        return text_formatted

    return clean_text(hit.get("description"))


def build_application_url(hit: dict[str, Any]) -> str | None:
    application_url = clean_text(get_nested(hit, "application_details", "url"))
    if application_url:
        return application_url

    webpage_url = clean_text(hit.get("webpage_url"))
    if webpage_url:
        return webpage_url

    ad_id = clean_text(hit.get("id"))
    if ad_id:
        return JOBTECH_AD_URL.format(ad_id=ad_id)

    return None


def map_jobtech_hit_to_job_listing(hit: dict[str, Any]) -> JobListing:
    return JobListing(
        title=clean_text(hit.get("headline")) or "Okänd titel",
        company=clean_text(get_nested(
            hit, "employer", "name")) or "Okänt företag",
        location=build_location(hit) or "Ej angivet",
        description=build_description(hit) or "Ingen beskrivning tillgänglig.",
        application_url=build_application_url(hit),
        work_mode=clean_text(get_nested(hit, "workplace_type", "label")),
        employment_type=clean_text(get_nested(
            hit, "employment_type", "label")),
        source_platform="Platsbanken",
    )


def normalize_text(value: str) -> str:
    return " ".join((value or "").lower().split())


def matches_location(job: JobListing, location: str) -> bool:
    wanted_location = normalize_text(location)

    if not wanted_location:
        return True

    job_location = normalize_text(job.location or "")
    return wanted_location in job_location


def matches_search_query(job: JobListing, query: str) -> bool:
    query_terms = [
        term
        for term in normalize_text(query).split()
        if len(term) >= 2
    ]

    if not query_terms:
        return True

    normalized_query = normalize_text(query)
    title = normalize_text(job.title or "")
    description = normalize_text(job.description or "")

    if normalized_query in title:
        return True

    title_matches = sum(1 for term in query_terms if term in title)
    description_matches = sum(1 for term in query_terms if term in description)

    if title_matches >= 2:
        return True

    if title_matches >= 1 and description_matches >= 1:
        return True

    return description_matches >= len(query_terms)


async def search_platsbanken_jobs(
    query: str,
    location: str,
    page: int = 1,
    limit: int = 100,
) -> tuple[list[JobListing], dict[str, Any]]:

    page = max(1, page)
    limit = max(1, min(limit, 100))
    offset = (page - 1) * limit

    search_query = query.strip()

    params = {
        "q": search_query,
        "limit": limit,
        "offset": offset,
    }

    diagnostics: dict[str, Any] = {
        "platform": "Platsbanken",
        "url": JOBTECH_SEARCH_URL,
        "fetched": False,
        "markdown_chars": 0,
        "jobs_extracted": 0,
        "after_score_filter": 0,
        "cached": False,
        "fetch_error": None,
        "search_query": search_query,
        "search_results_found": 0,
        "fallback_results_rejected": 0,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(JOBTECH_SEARCH_URL, params=params)
            response.raise_for_status()

        data = response.json()
        hits = data.get("hits", [])

        if not isinstance(hits, list):
            diagnostics["fetch_error"] = "Unexpected JobTech response: hits was not a list"
            return [], diagnostics

        jobs = [
            map_jobtech_hit_to_job_listing(hit)
            for hit in hits
            if isinstance(hit, dict)
        ]

        jobs = [
            job
            for job in jobs
            if matches_location(job, location) and matches_search_query(job, query)
        ]

        diagnostics["fetched"] = True
        diagnostics["jobs_extracted"] = len(jobs)
        diagnostics["search_results_found"] = len(hits)
        diagnostics["fallback_results_rejected"] = len(hits) - len(jobs)

        return jobs, diagnostics

    except Exception as exc:
        logger.warning("Platsbanken JobTech search failed: %s", exc)
        diagnostics["fetch_error"] = str(exc)
        return [], diagnostics
