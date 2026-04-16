import logging

from openai import RateLimitError

from models import JobListing, TailoredResumeResult
from services.ai_client import get_ai_client

AI_MODEL = "gemini-2.5-flash"
logger = logging.getLogger(__name__)


def build_resume_tailor_prompt(cv_text: str, target_job: JobListing) -> str:
    return (
        "Du är en svensk CV-specialist och rekryterare.\n"
        "Skapa ett skräddarsytt CV-utkast för kandidaten mot den valda rollen.\n\n"
        "Viktiga regler:\n"
        "- Hitta aldrig på erfarenhet, utbildning, certifikat, arbetsgivare, ansvar eller resultat.\n"
        "- Använd bara fakta som finns i kandidatens CV.\n"
        "- Om något viktigt saknas, lägg det i missing_but_not_invented istället för att hitta på.\n"
        "- Anpassa språk, nyckelord och prioritering mot jobbannonsen.\n"
        "- Skriv på svenska.\n"
        "- Gör innehållet konkret, ATS-vänligt och lätt att kopiera in i ett CV.\n\n"
        "Returnera:\n"
        "- target_role och target_company från jobbannonsen.\n"
        "- positioning_summary: kort strategi för hur kandidaten bör positioneras.\n"
        "- rewritten_profile: en förbättrad profiltext för CV:t.\n"
        "- sections: relevanta CV-sektioner med strategi, innehåll och bullet-förslag.\n"
        "- keywords_used: nyckelord du faktiskt använde i förslaget.\n"
        "- keywords_to_add: nyckelord kandidaten kan lägga till endast om de är sanna.\n"
        "- missing_but_not_invented: viktiga krav som saknas i CV:t och inte ska hittas på.\n"
        "- recruiter_notes: konkreta råd för nästa CV-redigering.\n\n"
        f"Jobbannons:\n"
        f"Titel: {target_job.title}\n"
        f"Företag: {target_job.company}\n"
        f"Plats: {target_job.location}\n"
        f"Arbetsform: {target_job.work_mode}\n"
        f"Anställningstyp: {target_job.employment_type}\n"
        f"Beskrivning:\n{target_job.description[:5000]}\n\n"
        f"Kandidatens CV:\n{cv_text[:12000]}"
    )


async def tailor_resume_with_ai(
    cv_text: str,
    target_job: JobListing,
) -> TailoredResumeResult | None:
    client = get_ai_client()
    prompt = build_resume_tailor_prompt(cv_text, target_job)

    try:
        response = await client.beta.chat.completions.parse(
            model=AI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Du skapar svenska, ATS-vänliga CV-utkast. "
                        "Du får aldrig hitta på meriter. "
                        "Du returnerar alltid strukturerad data enligt schemat."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            response_format=TailoredResumeResult,
        )

        parsed = response.choices[0].message.parsed

        if parsed is None:
            logger.warning("Resume tailoring returned no parsed result")
            return None

        return parsed

    except RateLimitError as e:
        logger.error(f"Resume tailoring quota/rate limit error: {e}")
        return None

    except Exception as e:
        logger.error(f"Resume tailoring error: {e}")
        return None