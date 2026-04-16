import asyncio

import streamlit as st

from models import JobListing, TailoredResumeResult
from services.resume_tailor import tailor_resume_with_ai
from utils.job_state import get_job_key


def build_tailored_resume_report(result: TailoredResumeResult) -> str:
    lines = [
        "Skräddarsytt CV-utkast",
        "",
        f"Målroll: {result.target_role}",
        f"Företag: {result.target_company}",
        "",
        "Positionering",
        result.positioning_summary,
        "",
        "Omskriven profil",
        result.rewritten_profile,
        "",
        "Sektioner",
    ]

    for section in result.sections:
        lines.extend([
            "",
            section.heading,
            f"Strategi: {section.strategy}",
        ])

        if section.content:
            lines.append("Innehåll:")
            lines.extend(f"- {item}" for item in section.content)

        if section.bullets:
            lines.append("Bullet-förslag:")
            for bullet in section.bullets:
                if bullet.original:
                    lines.append(f"- Original: {bullet.original}")
                lines.append(f"  Förslag: {bullet.tailored}")
                lines.append(f"  Varför: {bullet.reason}")

    lines.extend([
        "",
        "Nyckelord som används",
        ", ".join(result.keywords_used),
        "",
        "Nyckelord att lägga till om de är sanna",
        ", ".join(result.keywords_to_add),
        "",
        "Saknas men ska inte hittas på",
    ])
    lines.extend(f"- {item}" for item in result.missing_but_not_invented)

    lines.extend([
        "",
        "Rekryteraranteckningar",
    ])
    lines.extend(f"- {item}" for item in result.recruiter_notes)

    return "\n".join(lines)


def select_builder_target_job(saved_jobs: list[JobListing]) -> JobListing | None:
    if not saved_jobs:
        st.info("Spara ett jobb först för att kunna skapa ett skräddarsytt CV-utkast.")
        return None

    saved_job_options = {
        f"{job.title} — {job.company}": job
        for job in saved_jobs
    }

    selected_job_label = st.selectbox(
        "Välj sparat jobb",
        list(saved_job_options.keys()),
        key="tailored_resume_target_job",
    )

    return saved_job_options[selected_job_label]


def render_tailored_resume_result(result: TailoredResumeResult) -> None:
    st.write("**Positionering**")
    st.info(result.positioning_summary)

    st.write("**Omskriven profil**")
    st.text_area(
        "Omskriven profil",
        value=result.rewritten_profile,
        height=140,
        label_visibility="collapsed",
    )

    report_text = build_tailored_resume_report(result)
    st.download_button(
        label="Ladda ner skräddarsytt CV-utkast (.txt)",
        data=report_text,
        file_name="tailored_resume_draft.txt",
        mime="text/plain",
        use_container_width=True,
    )

    st.write("**Sektioner**")
    for section in result.sections:
        with st.expander(section.heading):
            st.write("**Strategi**")
            st.write(section.strategy)

            if section.content:
                st.write("**Innehåll**")
                for item in section.content:
                    st.write(f"- {item}")

            if section.bullets:
                st.write("**Bullet-förslag**")
                for bullet in section.bullets:
                    if bullet.original:
                        st.caption(f"Original: {bullet.original}")
                    st.write(f"- {bullet.tailored}")
                    st.caption(f"Varför: {bullet.reason}")

    col1, col2 = st.columns(2)

    with col1:
        st.write("**Nyckelord som används**")
        if result.keywords_used:
            st.write(", ".join(result.keywords_used))
        else:
            st.caption("Inga nyckelord returnerades.")

    with col2:
        st.write("**Nyckelord att lägga till om de är sanna**")
        if result.keywords_to_add:
            st.write(", ".join(result.keywords_to_add))
        else:
            st.caption("Inga extra nyckelord returnerades.")

    st.write("**Saknas men ska inte hittas på**")
    if result.missing_but_not_invented:
        for item in result.missing_but_not_invented:
            st.write(f"- {item}")
    else:
        st.caption("Inga tydliga saknade krav returnerades.")

    st.write("**Rekryteraranteckningar**")
    if result.recruiter_notes:
        for item in result.recruiter_notes:
            st.write(f"- {item}")
    else:
        st.caption("Inga rekryteraranteckningar returnerades.")


def render_tailored_resume_tab(final_cv_text: str) -> None:
    st.subheader("CV Builder")
    st.caption(
        "Skapa ett skräddarsytt CV-utkast mot ett sparat jobb utan att hitta på erfarenhet."
    )

    target_job = select_builder_target_job(st.session_state.saved_jobs)

    if target_job is None:
        return

    current_builder_key = get_job_key(target_job)

    if not final_cv_text.strip():
        st.info("Ladda upp ett CV eller klistra in CV-text för att skapa ett CV-utkast.")
        return

    if st.button("Skapa skräddarsytt CV-utkast", type="primary", use_container_width=True):
        with st.spinner("Skapar skräddarsytt CV-utkast..."):
            result = asyncio.run(tailor_resume_with_ai(final_cv_text, target_job))

            if result:
                st.session_state.tailored_resume_result = result
                st.session_state.last_tailored_cv_text = final_cv_text
                st.session_state.last_tailored_job_key = current_builder_key
            else:
                st.error(
                    "Kunde inte skapa CV-utkast just nu. Om du nyligen gjort flera AI-körningar kan Gemini-kvoten vara slut."
                )

    result = st.session_state.tailored_resume_result

    if (
        result
        and st.session_state.last_tailored_cv_text == final_cv_text
        and st.session_state.last_tailored_job_key == current_builder_key
    ):
        render_tailored_resume_result(result)