import logging

from models import JobListing, ScoringResult
from services.ai_client import get_ai_client

AI_MODEL = "gemini-2.5-flash"
logger = logging.getLogger(__name__)


async def score_jobs_with_ai(jobs: list[JobListing], skills: str) -> list[JobListing]:
    if not jobs:
        return []

    job_summaries = [
        f"[{i}] {j.title} @ {j.company} | {j.description[:2000]}"
        for i, j in enumerate(jobs)
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
                        "Returnera för varje jobb:\n"
                        "- score: ett heltal 0-100\n"
                        "- strengths: 2 till 4 korta styrkor på svenska\n"
                        "- gaps: 2 till 4 korta brister eller saknade krav på svenska\n"
                        "- recommendation: 1 kort rekommendation på svenska\n\n"
                        "Var kritisk. Hitta inte på erfarenhet som inte finns i CV:t. "
                        "Håll allt kort, tydligt och konkret."
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

        score_map = {s.index: s for s in response.choices[0].message.parsed.scored_jobs}

        for i, job in enumerate(jobs):
            if i in score_map:
                scored = score_map[i]
                job.match_score = scored.score
                job.match_strengths = scored.strengths
                job.match_gaps = scored.gaps
                job.match_recommendation = scored.recommendation

        jobs.sort(key=lambda j: j.match_score or 0, reverse=True)

    except Exception as e:
        logger.error(f"Scoring fel: {e}")

    return jobs
