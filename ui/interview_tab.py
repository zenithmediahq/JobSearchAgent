import asyncio

import streamlit as st

from models import InterviewAnswerFeedback, InterviewQuestion, JobListing
from services.interview_practice import (
    generate_interview_questions,
    score_interview_answers,
)
from utils.job_state import get_job_key


def select_interview_target_job(saved_jobs: list[JobListing]) -> JobListing | None:
    if not saved_jobs:
        st.info("Spara ett jobb först för att kunna öva intervju mot en specifik roll.")
        return None

    saved_job_options = {
        f"{job.title} — {job.company}": job
        for job in saved_jobs
    }

    selected_job_label = st.selectbox(
        "Välj sparat jobb",
        list(saved_job_options.keys()),
        key="interview_target_job",
    )

    return saved_job_options[selected_job_label]


def render_question_list(questions: list[InterviewQuestion]) -> list[str]:
    answers: list[str] = []

    for index, question in enumerate(questions, start=1):
        st.write(f"### Fråga {index}")
        st.write(f"**Kategori:** {question.category}")
        st.write(question.question)

        with st.expander("Vad ett bra svar bör innehålla"):
            for item in question.what_good_answers_include:
                st.write(f"- {item}")

        answer = st.text_area(
            f"Svar på fråga {index}",
            key=f"interview_answer_{question.id}",
            height=140,
            placeholder="Skriv ditt svar här...",
            label_visibility="collapsed",
        )
        answers.append(answer)

    return answers


def find_feedback_for_question(
    question_id: str,
    feedback_items: list[InterviewAnswerFeedback],
) -> InterviewAnswerFeedback | None:
    for item in feedback_items:
        if item.question_id == question_id:
            return item
    return None


def render_feedback(
    questions: list[InterviewQuestion],
    feedback_items: list[InterviewAnswerFeedback],
    overall_score: int,
    overall_summary: str,
) -> None:
    st.write("## Feedback")
    st.metric("Total intervjuscore", f"{overall_score}/100")
    st.info(overall_summary)

    report_text = build_interview_feedback_report(
        questions,
        feedback_items,
        overall_score,
        overall_summary,
    )

    st.download_button(
        label="Ladda ner intervjufeedback (.txt)",
        data=report_text,
        file_name="interview_feedback_report.txt",
        mime="text/plain",
        use_container_width=True,
    )

    for index, question in enumerate(questions, start=1):
        feedback = find_feedback_for_question(question.id, feedback_items)

        with st.expander(f"Feedback för fråga {index}: {question.question}"):
            if feedback is None:
                st.caption("Ingen feedback returnerades för denna fråga.")
                continue

            st.write(f"**Poäng:** {feedback.score}/100")

            st.write("**Styrkor**")
            if feedback.strengths:
                for item in feedback.strengths:
                    st.write(f"- {item}")
            else:
                st.caption("Inga styrkor returnerades.")

            st.write("**Svagheter**")
            if feedback.weaknesses:
                for item in feedback.weaknesses:
                    st.write(f"- {item}")
            else:
                st.caption("Inga svagheter returnerades.")

            st.write("**Förbättrat svar**")
            st.write(feedback.improved_answer)


def build_interview_feedback_report(
    questions: list[InterviewQuestion],
    feedback_items: list[InterviewAnswerFeedback],
    overall_score: int,
    overall_summary: str,
) -> str:
    lines = [
        "Intervjuövning Rapport",
        "",
        f"Total intervjuscore: {overall_score}/100",
        "",
        "Sammanfattning",
        overall_summary,
        "",
    ]

    for index, question in enumerate(questions, start=1):
        feedback = find_feedback_for_question(question.id, feedback_items)

        lines.extend([
            f"Fråga {index}",
            f"Kategori: {question.category}",
            f"Fråga: {question.question}",
        ])

        if question.what_good_answers_include:
            lines.append("Bra svar bör innehålla:")
            lines.extend(
                f"- {item}" for item in question.what_good_answers_include)

        if feedback is None:
            lines.extend([
                "Ingen feedback returnerades för denna fråga.",
                "",
            ])
            continue

        lines.extend([
            f"Poäng: {feedback.score}/100",
            "Styrkor",
        ])
        lines.extend(f"- {item}" for item in feedback.strengths)

        lines.extend([
            "Svagheter",
        ])
        lines.extend(f"- {item}" for item in feedback.weaknesses)

        lines.extend([
            "Förbättrat svar",
            feedback.improved_answer,
            "",
        ])

    return "\n".join(lines)


def render_interview_tab(final_cv_text: str) -> None:
    st.subheader("Intervju")
    st.caption(
        "Generera intervjufrågor mot ett sparat jobb och få AI-feedback på dina svar."
    )

    target_job = select_interview_target_job(st.session_state.saved_jobs)

    if target_job is None:
        return

    if not final_cv_text.strip():
        st.info(
            "Ladda upp ett CV eller klistra in CV-text för att använda intervjuträningen.")
        return

    current_job_key = get_job_key(target_job)

    if (
        final_cv_text != st.session_state.last_interview_cv_text
        or current_job_key != st.session_state.last_interview_job_key
    ):
        st.session_state.interview_question_set = None
        st.session_state.interview_feedback_set = None

    if st.button("Generera intervjufrågor", type="primary", use_container_width=True):
        with st.spinner("Genererar intervjufrågor..."):
            question_set = asyncio.run(
                generate_interview_questions(final_cv_text, target_job)
            )

            if question_set:
                st.session_state.interview_question_set = question_set
                st.session_state.interview_feedback_set = None
                st.session_state.last_interview_cv_text = final_cv_text
                st.session_state.last_interview_job_key = current_job_key
            else:
                st.error(
                    "Kunde inte generera intervjufrågor just nu. Om du nyligen gjort flera AI-körningar kan Gemini-kvoten vara slut."
                )

    question_set = st.session_state.interview_question_set

    if (
        question_set
        and st.session_state.last_interview_cv_text == final_cv_text
        and st.session_state.last_interview_job_key == current_job_key
    ):
        st.write(f"**Målroll:** {question_set.target_role}")
        st.write(f"**Företag:** {question_set.target_company}")

        answers = render_question_list(question_set.questions)

        if st.button("Utvärdera svar", use_container_width=True):
            non_empty_answers = [answer.strip()
                                 for answer in answers if answer.strip()]

            if not non_empty_answers:
                st.warning(
                    "Skriv minst ett svar innan du utvärderar intervjun.")
            else:
                with st.spinner("Bedömer dina svar..."):
                    feedback_set = asyncio.run(
                        score_interview_answers(
                            final_cv_text,
                            target_job,
                            question_set.questions,
                            answers,
                        )
                    )

                    if feedback_set:
                        st.session_state.interview_feedback_set = feedback_set
                    else:
                        st.error(
                            "Kunde inte utvärdera svaren just nu. Om du nyligen gjort flera AI-körningar kan Gemini-kvoten vara slut."
                        )

    feedback_set = st.session_state.interview_feedback_set

    if (
        question_set
        and feedback_set
        and st.session_state.last_interview_cv_text == final_cv_text
        and st.session_state.last_interview_job_key == current_job_key
    ):
        render_feedback(
            question_set.questions,
            feedback_set.feedback,
            feedback_set.overall_score,
            feedback_set.overall_summary,
        )
