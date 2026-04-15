import asyncio
import logging
import httpx
import urllib.parse

from typing import Any
from models import JobListing, JobListings
from services.ai_client import get_api_key, get_ai_client
from services.job_scoring import score_jobs_with_ai

LINKUP_API_URL = "https://api.linkup.so/v1/fetch"
AI_MODEL = "gemini-2.5-flash"
MAX_CONTENT_CHARS = 50000
SOURCE_EXTRACTION_CACHE: dict[str, tuple[list[JobListing], dict[str, Any]]] = {}

logger = logging.getLogger(__name__)


async def fetch_webpage(url: str) -> str:
    headers = {
        "Authorization": f"Bearer {get_api_key('LINKUP_API_KEY')}",
        "Content-Type": "application/json",
    }
    payload = {
        "url": url,
        "includeRawHtml": False,
        "renderJs": True,
        "extractImages": False,
    }

    async with httpx.AsyncClient(timeout=120) as client:
        try:
            response = await client.post(LINKUP_API_URL, headers=headers, json=payload)
            response.raise_for_status()
            return response.json().get("markdown", "")
        except Exception as e:
            logger.warning(f"Kunde inte läsa {url}: {e}")
            return ""


async def extract_jobs_with_ai(markdown: str, url: str) -> list[JobListing]:
    if not markdown:
        return []

    markdown = markdown[:MAX_CONTENT_CHARS]
    client = get_ai_client()

    try:
        response = await client.beta.chat.completions.parse(
            model=AI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extrahera alla jobbannonser. Identifiera titel, företag, plats, länk, "
                        "arbetsform (distans/hybrid/på plats), anställningstyp (heltid/deltid) "
                        "och beskrivning."
                    ),
                },
                {"role": "user", "content": f"URL: {url}\n\nInnehåll:\n{markdown}"},
            ],
            response_format=JobListings,
        )
        
        parsed = response.choices[0].message.parsed

        if parsed is None:
            logger.warning(f"AI extraction returned no parsed jobs for {url}")
            return []

        return parsed.jobs
    except Exception as e:
        logger.error(f"AI Extraktionsfel: {e}")
        return []

async def fetch_and_extract_source(source: dict[str, str]) -> tuple[list[JobListing], dict[str, Any]]:
    cache_key = source["url"]

    if cache_key in SOURCE_EXTRACTION_CACHE:
        cached_jobs, cached_diagnostics = SOURCE_EXTRACTION_CACHE[cache_key]

        jobs = [job.model_copy(deep=True) for job in cached_jobs]
        diagnostics = dict(cached_diagnostics)
        diagnostics["cached"] = True

        return jobs, diagnostics

    diagnostics: dict[str, Any] = {
        "platform": source["platform"],
        "url": source["url"],
        "fetched": False,
        "markdown_chars": 0,
        "jobs_extracted": 0,
        "after_score_filter": 0,
        "cached": False,
    }

    md = await fetch_webpage(source["url"])
    diagnostics["markdown_chars"] = len(md)

    if md.strip():
        diagnostics["fetched"] = True

    extracted = await extract_jobs_with_ai(md, source["url"])
    diagnostics["jobs_extracted"] = len(extracted)

    for job in extracted:
        job.source_platform = source["platform"]

    SOURCE_EXTRACTION_CACHE[cache_key] = (
        [job.model_copy(deep=True) for job in extracted],
        dict(diagnostics),
    )

    return extracted, diagnostics


async def run_search_workflow(
    query: str,
    location: str,
    skills: str,
    min_score: int,
    selected_sources: list[str] | None = None,
) -> tuple[list[JobListing], dict[str, Any]]:
    q_enc = urllib.parse.quote(query)
    l_enc = urllib.parse.quote(location)

    sources = [
        {
            "url": f"https://arbetsformedlingen.se/platsbanken/annonser?q={q_enc}%20{l_enc}",
            "platform": "Platsbanken",
        },
        {
            "url": f"https://se.indeed.com/jobs?q={q_enc}&l={l_enc}",
            "platform": "Indeed",
        },
        {
            "url": f"https://www.linkedin.com/jobs/search?keywords={q_enc}&location={l_enc}",
            "platform": "LinkedIn",
        },
        {
            "url": f"https://jobbsafari.se/jobb?q={q_enc}&l={l_enc}",
            "platform": "JobbSafari",
        },
    ]

    if selected_sources is not None:
        selected_source_names = set(selected_sources)
        sources = [
            source for source in sources
            if source["platform"] in selected_source_names
        ]

    if not sources:
        diagnostics: dict[str, Any] = {
            "sources": [],
            "before_dedup": 0,
            "after_dedup": 0,
            "after_score_filter": 0,
        }
        return [], diagnostics

    results = await asyncio.gather(*(fetch_and_extract_source(source) for source in sources))

    diagnostics_by_source: list[dict[str, Any]] = []
    all_jobs_raw: list[JobListing] = []

    for extracted_jobs, source_diag in results:
        diagnostics_by_source.append(source_diag)
        all_jobs_raw.extend(extracted_jobs)

    before_dedup = len(all_jobs_raw)

    all_jobs: list[JobListing] = []
    seen_jobs: set[str] = set()

    for job in all_jobs_raw:
        title_key = (job.title or "").lower().strip()
        company_key = (job.company or "").lower().strip()
        key = f"{title_key}|{company_key}"

        if key not in seen_jobs:
            seen_jobs.add(key)
            all_jobs.append(job)

    after_dedup = len(all_jobs)

    scored_jobs = await score_jobs_with_ai(all_jobs, skills)
    filtered_jobs = [job for job in scored_jobs if (job.match_score or 0) >= min_score]

    for source_diag in diagnostics_by_source:
        platform = source_diag["platform"]
        source_diag["after_score_filter"] = sum(
            1 for job in filtered_jobs if job.source_platform == platform
        )

    diagnostics: dict[str, Any] = {
        "sources": diagnostics_by_source,
        "before_dedup": before_dedup,
        "after_dedup": after_dedup,
        "after_score_filter": len(filtered_jobs),
    }

    return filtered_jobs, diagnostics


