import logging

from models import JobListing, ResumeScanResult
from openai import APIStatusError, OpenAIError, RateLimitError
from services.ai_client import get_ai_client

AI_MODEL = "gemini-2.5-flash"
logger = logging.getLogger(__name__)


def build_resume_scan_prompt(cv_text: str, target_job: JobListing | None = None) -> str:
    job_context = "Ingen specifik jobbannons är vald. Gör en generell ATS-granskning av CV:t."

    if target_job:
        job_context = (
            "Granska CV:t mot denna jobbannons.\n\n"
            f"Jobbtitel: {target_job.title}\n"
            f"Företag: {target_job.company}\n"
            f"Plats: {target_job.location}\n"
            f"Arbetsform: {target_job.work_mode}\n"
            f"Anställningstyp: {target_job.employment_type}\n"
            f"Jobbeskrivning:\n{target_job.description[:4000]}"
        )

    return (
        "Du är en svensk ATS- och rekryteringsspecialist.\n"
        "Analysera kandidatens CV och returnera en konkret, praktisk CV-granskning på svenska.\n\n"
        "Viktiga regler:\n"
        "- Hitta aldrig på erfarenhet, utbildning, certifikat, titlar eller prestationer.\n"
        "- Föreslå bara förbättringar som bygger på information som redan finns i CV:t.\n"
        "- Var konkret och användbar, inte allmänt uppmuntrande.\n"
        "- Poäng ska vara heltal mellan 0 och 100.\n"
        "- Om något saknas i CV:t, säg att det saknas.\n\n"
        f"{job_context}\n\n"
        f"Kandidatens CV:\n{cv_text[:12000]}"
    )


async def scan_resume_with_ai(
    cv_text: str,
    target_job: JobListing | None = None,
) -> ResumeScanResult | None:
    client = get_ai_client()
    prompt = build_resume_scan_prompt(cv_text, target_job)

    try:
        response = await client.beta.chat.completions.parse(
            model=AI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Du analyserar CV:n för ATS-kompatibilitet, tydlighet och matchning. "
                        "Du returnerar alltid strukturerad data enligt schemat. "
                        "Du skriver på svenska."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            response_format=ResumeScanResult,
        )

        parsed = response.choices[0].message.parsed

        if parsed is None:
            logger.warning("Resume scan returned no parsed result")
            return None
        return parsed
    
    except RateLimitError as e:
        logger.error(f"Resume scan quota/rate limit error: {e}")
        return None

    except APIStatusError as e:
        logger.error(f"Resume scan API status error: {e}")
        return None

    except OpenAIError as e:
        logger.error(f"Resume scan OpenAI-compatible API error: {e}")
        return None

    except Exception:
        logger.exception("Unexpected resume scan error")
        return None