
import logging

from models import JobListing, ApplicationPack
from services.ai_client import get_ai_client

AI_MODEL = "gemini-2.5-flash"
logger = logging.getLogger(__name__)


async def generate_application_pack(job: JobListing, cv_text: str) -> ApplicationPack | None:
    client = get_ai_client()

    try:
        response = await client.beta.chat.completions.parse(
            model=AI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Du hjälper kandidaten att skriva ett ansökningspaket på svenska. "
                        "Du får kandidatens riktiga CV och en jobbannons. "
                        "Du får aldrig hitta på erfarenhet, utbildning, certifikat eller ansvar som inte finns i CV:t. "
                        "Skriv tydligt, konkret och professionellt. Undvik överdrivet språk.\n\n"
                        "Returnera:\n"
                        "- short_motivation: 2 till 4 meningar, kort och användbar för ansökningsformulär\n"
                        "- cover_letter: ett kort personligt brev på svenska\n"
                        "- cv_tailoring_tips: 3 till 6 konkreta tips om vad kandidaten bör lyfta fram eller justera i sitt CV för detta jobb"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Kandidatens CV:\n{cv_text}\n\n"
                        f"Jobb:\n"
                        f"Titel: {job.title}\n"
                        f"Företag: {job.company}\n"
                        f"Plats: {job.location}\n"
                        f"Arbetsform: {job.work_mode}\n"
                        f"Anställningstyp: {job.employment_type}\n"
                        f"Beskrivning:\n{job.description[:4000]}"
                    ),
                },
            ],
            response_format=ApplicationPack,
        )
        return response.choices[0].message.parsed
    except Exception as e:
        logger.error(f"Application pack fel: {e}")
        return None
