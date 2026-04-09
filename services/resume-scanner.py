import logging

from models import JobListing, ResumeScanResult
from services.ai_client import get_ai_client

AI_MODEL = "gemini-2.5-flash"
logger = logging.getLogger(_Name_)


def build_resume_scan_prompt(cv_text: str, target_job: JobListing | None = None) -> str:
    if not target_job:
        return (
            f"Kandidatens CV:\n{cv_text}\n\n"
            "Analysera CV:t ur ett ATS- och rekryterarperspektiv. "
            "Bedöm innehållets tydlighet. relevans, struktur och sökordsstyrka."
        )

    return (
        f"Kandidatens CV:\n{cv_text}\n\n"
        "Måljobb: \n"
        f"Titel: {target_job.title}\n"
        f"Företag: {target_job.company\n"
        f"Plats: {target_job.location\n"
        f"Arbetsform: {target_job.work_mode\n"
        f"Anställningstyp: {target_job.employment_type\n"
        f"Beskrivning:\n{target_job.description[:4000]}\n\n"
        "Analysera CV:t mot jobbet ur ett ATS- och rekryterarperspektiv. "
        "Identifiera vilka viktiga nyckelord och krav som saknas eller är svaga."
    )


async def scan_resume_with_ai(
    cv_text: str,
    target_job: JobListing | None = None,
) -> ResumeScanResult | None:
    client = get_ai_client()

    try:
        response = await client.beta.chat.completions.parse(
            model=AI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Du analyserar CV:n för jobbsökande på svenska. "
                        "Var konkret, kritisk och hjälpsam. "
                        "Du får aldrig hitta på erfarenhet, utbildning, certifikat eller resultat. "
                        "Returnera en strukturerad ATS-analys av CV:t.\n\n"
                        "Regler:\n"
                        "- overall_score: heltal 0-100\n"
                        "- summary: 2 till 4 meningar\n"
                        "- strengths: 3 till 6 konkreta styrkor\n"
                        "- weaknesses: 3 till 6 konkreta svagheter\n"
                        "- missing_sections: lista över viktiga sektioner som saknas eller är mycket svaga\n"
                        "- ats_risks: lista över risker som kan försämra ATS-läsbarhet eller tydlighet\n"
                        "- section_scores: bedöm minst sektionerna summary, experience, education, skills\n"
                        "- keyword_gaps: viktiga nyckelord eller krav, markera om de finns i CV:t eller inte\n"
                        "- bullet_suggestions: förbättra svaga CV-punkter utan att hitta på nya fakta\n"
                        "- recommended_keywords: lista över relevanta nyckelord kandidaten bör lyfta fram om de är sanna"
                    ),
                },
                {
                    "role": "user",
                    "content": build_resume_scan_prompt(cv_text, target_job),
                },
            ],
            response_format=ResumeScanResult,
        )
        return response.choices[0].message.parsed
    except Exception as exc:
        logger.error("Resume scanner error: %s", exc)
        return None
