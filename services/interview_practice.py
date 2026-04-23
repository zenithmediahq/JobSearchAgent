import logging

from openai import APIStatusError, OpenAIError, RateLimitError

from models import (
    InterviewFeedbackSet,
    InterviewQuestion,
    InterviewQuestionSet,
    JobListing,
)

from services.ai_client import get_ai_client

AI_MODEL = "gemini-2.5-flash"
logger = logging.getLogger(__name__)


def build_interview_question_prompt(cv_text: str, target_job: JobListing) -> str:
    return (
        "Du är en svensk rekryterare och intervjuförberedare.\n"
        "Skapa en realistisk uppsättning intervjufrågor baserat på kandidatens riktiga CV och den valda jobbannonsen.\n\n"
        "Viktiga regler:\n"
        "- Frågorna ska kännas relevanta för den specifika rollen.\n"
        "- Blanda kategorier som behavioral, technical, motivation och role-fit.\n"
        "- Hitta aldrig på erfarenhet som kandidaten inte har.\n"
        "- what_good_answers_include ska vara korta punkter om vad ett starkt svar bör täcka.\n"
        "- Skriv på svenska.\n\n"
        f"Jobbannons:\n"
        f"Titel: {target_job.title}\n"
        f"Företag: {target_job.company}\n"
        f"Plats: {target_job.location}\n"
        f"Arbetsform: {target_job.work_mode}\n"
        f"Anställningstyp: {target_job.employment_type}\n"
        f"Beskrivning:\n{target_job.description[:5000]}\n\n"
        f"Kandidatens CV:\n{cv_text[:12000]}"
    )


def build_interview_feedback_prompt(
    cv_text: str,
    target_job: JobListing,
    questions: list[InterviewQuestion],
    answers: list[str],
) -> str:
    question_blocks = []

    for question, answer in zip(questions, answers):
        question_blocks.append(
            f"Fråga-ID: {question.id}\n"
            f"Kategori: {question.category}\n"
            f"Fråga: {question.question}\n"
            f"Bra svar bör innehålla: {', '.join(question.what_good_answers_include)}\n"
            f"Kandidatens svar: {answer.strip() or '[Inget svar]'}"
        )

    joined_questions = "\n\n".join(question_blocks)

    return (
        "Du är en svensk intervjuförberedare och rekryterare.\n"
        "Bedöm kandidatens svar på intervjufrågor baserat på kandidatens riktiga CV och den valda jobbannonsen.\n\n"
        "Viktiga regler:\n"
        "- Var konkret, rättvis och användbar.\n"
        "- Hitta aldrig på erfarenhet, resultat eller tekniska kunskaper som inte finns i CV:t.\n"
        "- improved_answer ska vara en förbättrad version av svaret, men bara byggd på uppgifter som rimligen finns i CV:t eller i kandidatens eget svar.\n"
        "- score ska vara ett heltal mellan 0 och 100.\n"
        "- Skriv på svenska.\n\n"
        f"Jobbannons:\n"
        f"Titel: {target_job.title}\n"
        f"Företag: {target_job.company}\n"
        f"Plats: {target_job.location}\n"
        f"Arbetsform: {target_job.work_mode}\n"
        f"Anställningstyp: {target_job.employment_type}\n"
        f"Beskrivning:\n{target_job.description[:5000]}\n\n"
        f"Kandidatens CV:\n{cv_text[:12000]}\n\n"
        f"Intervjufrågor och svar:\n{joined_questions}"
    )


async def generate_interview_questions(
    cv_text: str,
    target_job: JobListing,
) -> InterviewQuestionSet | None:
    client = get_ai_client()
    prompt = build_interview_question_prompt(cv_text, target_job)

    try:
        response = await client.beta.chat.completions.parse(
            model=AI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Du skapar strukturerade intervjufrågor på svenska. "
                        "Returnera alltid strukturerad data enligt schemat."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            response_format=InterviewQuestionSet,
        )

        parsed = response.choices[0].message.parsed

        if parsed is None:
            logger.warning(
                "Interview question generation returned no parsed result")
            return None

        return parsed

    except RateLimitError as exc:
        logger.error("Interview question generation rate limit error: %s", exc)
        return None

    except APIStatusError as exc:
        logger.error("Interview question generation API status error: %s", exc)
        return None

    except OpenAIError as exc:
        logger.error(
            "Interview question generation OpenAI-compatible API error: %s", exc)
        return None

    except Exception:
        logger.exception("Unexpected interview question generation error")
        return None


async def score_interview_answers(
    cv_text: str,
    target_job: JobListing,
    questions: list[InterviewQuestion],
    answers: list[str],
) -> InterviewFeedbackSet | None:
    client = get_ai_client()
    prompt = build_interview_feedback_prompt(
        cv_text, target_job, questions, answers)

    try:
        response = await client.beta.chat.completions.parse(
            model=AI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Du bedömer intervjusvar på svenska och returnerar alltid strukturerad feedback enligt schemat. "
                        "Du får aldrig hitta på meriter."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            response_format=InterviewFeedbackSet,
        )

        parsed = response.choices[0].message.parsed

        if parsed is None:
            logger.warning(
                "Interview answer scoring returned no parsed result")
            return None

        return parsed

    except RateLimitError as exc:
        logger.error("Interview answer scoring rate limit error: %s", exc)
        return None

    except APIStatusError as exc:
        logger.error("Interview answer scoring API status error: %s", exc)
        return None

    except OpenAIError as exc:
        logger.error(
            "Interview answer scoring OpenAI-compatible API error: %s", exc)
        return None

    except Exception:
        logger.exception("Unexpected interview answer scoring error")
        return None
