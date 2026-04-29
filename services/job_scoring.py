import hashlib
import logging
import re

from models import JobListing, ScoringResult
from services.ai_client import get_ai_client

AI_MODEL = "gemini-2.5-flash"
SCORING_CACHE: dict[str, list[JobListing]] = {}
logger = logging.getLogger(__name__)

STOP_WORDS = {
    "och", "att", "det", "som", "med", "for", "för", "till", "ett", "den", "din",
    "har", "kan", "ska", "vill", "inom", "fran", "från", "vara", "eller", "the",
    "and", "with", "you", "are", "this", "that",
}


def normalize_words(value: str) -> set[str]:
    words = re.findall(r"[a-zA-ZåäöÅÄÖ0-9+#.-]{3,}", (value or "").lower())
    return {word for word in words if word not in STOP_WORDS}


def build_job_identity(job: JobListing) -> str:
    description_digest = hashlib.sha256(
        (job.description or "").strip().lower()[:4000].encode("utf-8")
    ).hexdigest()[:16]

    return "|".join([
        (job.title or "").strip().lower(),
        (job.company or "").strip().lower(),
        (job.location or "").strip().lower(),
        (job.source_platform or "").strip().lower(),
        description_digest,
    ])


def build_scoring_cache_key(jobs: list[JobListing], skills: str) -> str:
    job_identities = sorted(build_job_identity(job) for job in jobs)
    raw_key = "\n".join([
        skills.strip(),
        *job_identities,
    ])
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def apply_fallback_scores(jobs: list[JobListing], skills: str) -> list[JobListing]:
    cv_words = normalize_words(skills)

    for job in jobs:
        title_words = normalize_words(job.title or "")
        description_words = normalize_words(job.description or "")

        title_overlap = cv_words & title_words
        description_overlap = cv_words & description_words

        score = 15
        score += min(len(title_overlap) * 10, 35)
        score += min(len(description_overlap) * 2, 30)

        if job.source_platform == "Platsbanken":
            score += 5

        if not title_overlap and len(description_overlap) < 3:
            score = 20

        score = min(score, 80)

        job.match_score = score
        job.match_strengths = [
            f"Matchar {len(title_overlap)} ord i titeln och {len(description_overlap)} ord i annonsen från CV:t.",
        ]
        job.match_gaps = [
            "Detta är en förenklad nyckelordsbedömning eftersom AI-score inte kunde köras.",
        ]
        job.match_recommendation = (
            "Använd som preliminär ranking. Kör AI-score igen när API-kvoten fungerar."
        )

    jobs.sort(key=lambda item: item.match_score or 0, reverse=True)
    return jobs


async def score_jobs_with_ai(jobs: list[JobListing], skills: str) -> list[JobListing]:
    if not jobs:
        return []

    cache_key = build_scoring_cache_key(jobs, skills)

    if cache_key in SCORING_CACHE:
        logger.info("Using cached AI scoring result")
        return [job.model_copy(deep=True) for job in SCORING_CACHE[cache_key]]

    job_summaries = [
        f"[{i}] {job.title} @ {job.company} | {job.description[:2000]}"
        for i, job in enumerate(jobs)
    ]

    client = get_ai_client()

    try:
        response = await client.beta.chat.completions.parse(
            model=AI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Du är en stenhård rekryterare. "
                        "Betygsätt varje jobb 0-100 baserat på hur väl kandidatens CV matchar kraven. "
                        "Returnera för varje jobb score, strengths, gaps och recommendation. "
                        "Var kritisk. Hitta inte på erfarenhet som inte finns i CV:t. "
                        "Håll allt kort, tydligt och konkret på svenska."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Kandidatens CV:\n{skills}\n\n"
                        f"Jobbannonser:\n{chr(10).join(job_summaries)}"
                    ),
                },
            ],
            response_format=ScoringResult,
        )

        parsed = response.choices[0].message.parsed

        if parsed is None:
            logger.warning("AI scoring returned no parsed result")
            jobs = apply_fallback_scores(jobs, skills)
            SCORING_CACHE[cache_key] = [
                job.model_copy(deep=True) for job in jobs]
            return jobs

        score_map = {scored.index: scored for scored in parsed.scored_jobs}

        for index, job in enumerate(jobs):
            scored = score_map.get(index)

            if scored is None:
                continue

            job.match_score = scored.score
            job.match_strengths = scored.strengths
            job.match_gaps = scored.gaps
            job.match_recommendation = scored.recommendation

        unscored_jobs = [job for job in jobs if job.match_score is None]
        if unscored_jobs:
            logger.warning(
                "AI scoring missed %s jobs; applying fallback", len(unscored_jobs))
            apply_fallback_scores(unscored_jobs, skills)

        jobs.sort(key=lambda item: item.match_score or 0, reverse=True)
        SCORING_CACHE[cache_key] = [job.model_copy(deep=True) for job in jobs]
        return jobs

    except Exception:
        logger.exception("AI scoring failed; using fallback scoring")
        jobs = apply_fallback_scores(jobs, skills)
        SCORING_CACHE[cache_key] = [job.model_copy(deep=True) for job in jobs]
        return jobs
