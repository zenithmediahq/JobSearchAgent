import asyncio
import logging
import httpx
import urllib.parse
from collections.abc import Callable
import unicodedata

from typing import Any
from models import JobListing, JobListings
from services.ai_client import get_api_key, get_ai_client
from services.job_scoring import score_jobs_with_ai

LINKUP_API_URL = "https://api.linkup.so/v1/fetch"
LINKUP_SEARCH_API_URL = "https://api.linkup.so/v1/search"
AI_MODEL = "gemini-2.5-flash"
MAX_CONTENT_CHARS = 50000
SOURCE_EXTRACTION_CACHE: dict[str,
                              tuple[list[JobListing], dict[str, Any]]] = {}
SourceConfig = dict[str, str]

logger = logging.getLogger(__name__)


def classify_fetch_error(platform: str, error_message: str | None) -> str | None:
    if not error_message:
        return None

    normalized = error_message.lower()

    if "http 400" in normalized and "fetch_error" in normalized:
        if platform == "Indeed":
            return "Indeed blocked or unsupported by fetch provider"
        if platform == "LinkedIn":
            return "LinkedIn blocked or unsupported by fetch provider"
        return "Source blocked or unsupported by fetch provider"

    return error_message


async def search_web(
    query: str,
    include_domains: list[str] | None = None,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    headers = {
        "Authorization": f"Bearer {get_api_key('LINKUP_API_KEY')}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "q": query,
        "depth": "standard",
        "outputType": "searchResults",
        "includeSources": False,
        "includeImages": False,
        "maxResults": max_results,
    }

    if include_domains:
        payload["includeDomains"] = include_domains

    async with httpx.AsyncClient(timeout=120) as client:
        try:
            response = await client.post(
                LINKUP_SEARCH_API_URL,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            return response.json().get("results", [])
        except Exception as exc:
            logger.warning("Linkup search failed for %s: %s", query, exc)
            return []


async def fetch_webpage(url: str) -> tuple[str, str | None]:
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
            return response.json().get("markdown", ""), None

        except httpx.HTTPStatusError as e:
            error_message = f"HTTP {e.response.status_code}: {e.response.text[:300]}"
            logger.warning(f"Kunde inte läsa {url}: {error_message}")
            return "", error_message

        except Exception as e:
            error_message = str(e)
            logger.warning(f"Kunde inte läsa {url}: {error_message}")
            return "", error_message


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
                        "Extrahera jobb från sidan. "
                        "Sidan kan vara antingen en sökresultatsida med flera jobbkort eller en enskild jobbannons. "
                        "Om det är en lista med jobb, extrahera varje synligt jobb så gott det går även om vissa fält saknas. "
                        "Om information saknas, använd tom sträng istället för att hitta på fakta. "
                        "Identifiera titel, företag, plats, länk, arbetsform, anställningstyp och en kort beskrivning när det finns. "
                        "Returnera alla synliga jobb som strukturerad data."
                    ),
                },
                {
                    "role": "user",
                    "content": f"URL: {url}\n\nInnehåll:\n{markdown}",
                },
            ],
            response_format=JobListings,
        )

        parsed = response.choices[0].message.parsed

        if parsed is None:
            logger.warning(f"AI extraction returned no parsed jobs for {url}")
            return []

        return parsed.jobs

    except Exception as e:
        logger.error(f"AI Extraktionsfel för {url}: {e}")
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

    md, fetch_error = await fetch_webpage(source["url"])
    diagnostics["fetch_error"] = classify_fetch_error(
        source["platform"],
        fetch_error,
    )

    diagnostics["markdown_chars"] = len(md)

    if md.strip():
        diagnostics["fetched"] = True

    extracted = await extract_jobs_with_ai(md, source["url"])
    diagnostics["jobs_extracted"] = len(extracted)

    for job in extracted:
        job.source_platform = source["platform"]

    if diagnostics["fetch_error"] is None:
        SOURCE_EXTRACTION_CACHE[cache_key] = (
            [job.model_copy(deep=True) for job in extracted],
            dict(diagnostics),
        )

    return extracted, diagnostics


def build_source_configs(
    query: str,
    location: str,
    pages_per_source: int,
) -> list[SourceConfig]:
    q_enc = urllib.parse.quote(query)
    l_enc = urllib.parse.quote(location)
    pages_per_source = max(1, min(pages_per_source, 3))

    sources: list[SourceConfig] = []

    for page in range(1, pages_per_source + 1):
        sources.append(
            {
                "url": (
                    "https://arbetsformedlingen.se/platsbanken/annonser"
                    f"?q={q_enc}%20{l_enc}&page={page}"
                ),
                "platform": "Platsbanken",
                "query": query,
                "location": location,
            }
        )

    sources.extend(
        [
            {
                "url": f"https://se.indeed.com/jobs?q={q_enc}&l={l_enc}",
                "platform": "Indeed",
                "query": query,
                "location": location,
            },
            {
                "url": f"https://www.linkedin.com/jobs/search?keywords={q_enc}&location={l_enc}",
                "platform": "LinkedIn",
                "query": query,
                "location": location,
            },
            {
                "url": f"https://jobbsafari.se/jobb?q={q_enc}&l={l_enc}",
                "platform": "JobbSafari",
                "query": query,
                "location": location,
            },
        ]
    )

    return sources


def is_probable_job_posting(title: str, url: str, content: str) -> bool:
    normalized_title = (title or "").lower()
    normalized_url = (url or "").lower()
    normalized_content = (content or "").lower()

    blocked_title_fragments = [
        "lediga jobb för",
        "jobb som",
        "jobs in",
        "jobs for",
        "lön i",
        "salary",
        "matchar",
    ]

    blocked_url_fragments = [
        "/jobs?",
        "/jobs/search",
        "/q-",
        "salary",
    ]

    if any(fragment in normalized_title for fragment in blocked_title_fragments):
        return False

    if any(fragment in normalized_url for fragment in blocked_url_fragments):
        return False

    # Keep pages that look like a specific role/company posting.
    positive_signals = [
        " söker ",
        "hiring",
        "jobb",
        "job",
        "support",
        "specialist",
        "tekniker",
        "servicedesk",
        "helpdesk",
    ]

    return any(signal in normalized_title or signal in normalized_content for signal in positive_signals)


async def search_source_jobs(source: SourceConfig) -> tuple[list[JobListing], dict[str, Any]]:
    platform = source["platform"]
    url = source["url"]

    diagnostics: dict[str, Any] = {
        "platform": platform,
        "url": url,
        "fetched": False,
        "markdown_chars": 0,
        "jobs_extracted": 0,
        "after_score_filter": 0,
        "cached": False,
        "fetch_error": None,
        "search_results_found": 0,
        "search_query": None,
    }

    domain_map = {
        "Indeed": ["se.indeed.com"],
        "LinkedIn": ["linkedin.com"],
    }

    search_query_map = {
        "Indeed": f'"{source["query"]}" "{source["location"]}" jobb site:se.indeed.com',
        "LinkedIn": f'"{source["query"]}" "{source["location"]}" jobs site:linkedin.com/jobs',
    }

    search_results = await search_web(
        query=search_query,
        include_domains=domain_map.get(platform),
        max_results=10,
    )

    diagnostics["search_results_found"] = len(search_results)

    jobs: list[JobListing] = []

    for result in search_results:
        result_url = result.get("url", "")
        result_name = result.get("name", "")
        result_content = result.get("content", "")

        if not result_url and not result_name and not result_content:
            continue

        if not is_probable_job_posting(result_name, result_url, result_content):
            continue

        jobs.append(
            JobListing(
                title=result_name or "Okänd titel",
                company="Okänt företag",
                location="Ej angivet",
                description=result_content or "Ingen beskrivning tillgänglig.",
                application_url=result_url or None,
                source_platform=platform,
            )
        )

    diagnostics["fetched"] = bool(search_results)
    diagnostics["jobs_extracted"] = len(jobs)

    if not jobs:
        diagnostics[
            "fetch_error"] = f"No jobs returned from Linkup search fallback for {platform}"

    return jobs, diagnostics


async def fetch_source_jobs(source: SourceConfig) -> tuple[list[JobListing], dict[str, Any]]:
    platform = source["platform"]

    if platform == "Platsbanken":
        return await fetch_and_extract_source(source)

    if platform == "Indeed":
        jobs, diagnostics = await fetch_and_extract_source(source)
        if jobs:
            return jobs, diagnostics
        return await search_source_jobs(source)

    if platform == "LinkedIn":
        jobs, diagnostics = await fetch_and_extract_source(source)
        if jobs:
            return jobs, diagnostics
        return await search_source_jobs(source)

    if platform == "JobbSafari":
        return await fetch_and_extract_source(source)

    diagnostics: dict[str, Any] = {
        "platform": platform,
        "url": source["url"],
        "fetched": False,
        "markdown_chars": 0,
        "jobs_extracted": 0,
        "after_score_filter": 0,
        "cached": False,
        "fetch_error": "Unsupported source",
    }
    return [], diagnostics


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower().strip()

    for char in [",", ".", "!", "?", ":", ";", "|", "-", "(", ")", "/"]:
        normalized = normalized.replace(char, " ")

    normalized = " ".join(normalized.split())
    return normalized


def normalize_job_title(title: str, location: str | None = None) -> str:
    normalized_title = normalize_text(title)

    if not location:
        return normalized_title

    normalized_location = normalize_text(location)
    location_tokens = {
        token
        for token in normalized_location.split()
        if len(token) > 2
    }

    filtered_tokens = [
        token
        for token in normalized_title.split()
        if token not in location_tokens
    ]

    return " ".join(filtered_tokens)


async def run_search_workflow(
    query: str,
    location: str,
    skills: str,
    min_score: int,
    selected_sources: list[str] | None = None,
    filter_by_score: bool = True,
    pages_per_source: int = 1,
) -> tuple[list[JobListing], dict[str, Any]]:
    sources = build_source_configs(query, location, pages_per_source)

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
            "score_filter_enabled": filter_by_score,
            "returned_results": 0,
        }
        return [], diagnostics

    results = await asyncio.gather(
        *(fetch_source_jobs(source) for source in sources)
    )

    diagnostics_by_source: list[dict[str, Any]] = []
    all_jobs_raw: list[JobListing] = []

    for extracted_jobs, source_diag in results:
        diagnostics_by_source.append(source_diag)
        all_jobs_raw.extend(extracted_jobs)

    before_dedup = len(all_jobs_raw)

    all_jobs: list[JobListing] = []
    seen_jobs: set[str] = set()

    for job in all_jobs_raw:
        title_key = normalize_job_title(job.title or "", job.location)
        company_key = (job.company or "").lower().strip()
        location_key = (job.location or "").lower().strip()
        key = f"{title_key}|{company_key}|{location_key}"

        if key not in seen_jobs:
            seen_jobs.add(key)
            all_jobs.append(job)

    after_dedup = len(all_jobs)

    scored_jobs = await score_jobs_with_ai(all_jobs, skills)
    matched_jobs = [job for job in scored_jobs if (
        job.match_score or 0) >= min_score]
    returned_jobs = matched_jobs if filter_by_score else scored_jobs

    for source_diag in diagnostics_by_source:
        platform = source_diag["platform"]
        source_diag["after_score_filter"] = sum(
            1 for job in matched_jobs if job.source_platform == platform
        )

    diagnostics: dict[str, Any] = {
        "sources": diagnostics_by_source,
        "before_dedup": before_dedup,
        "after_dedup": after_dedup,
        "after_score_filter": len(matched_jobs),
        "score_filter_enabled": filter_by_score,
        "returned_results": len(returned_jobs),
    }

    return returned_jobs, diagnostics
