import asyncio

import streamlit as st

from models import JobListing, ResumeScanResult
from services.resume_scanner import scan_resume_with_ai
from utils.job_state import get_job_key


def build_resume_scan_report(result: ResumeScanResult) -> str:
    lines = [
        "CV Scanner Rapport",
        "",
        f"ATS-score: {result.overall_score}/100",
        "",
        "Sammanfattning",
        result.summary,
        "",
        "Styrkor",
    ]

    lines.extend(f"- {item}" for item in result.strengths)

    lines.extend([
        "",
        "Svagheter",
    ])
    lines.extend(f"- {item}" for item in result.weaknesses)

    lines.extend([
        "",
        "Saknade sektioner",
    ])
    lines.extend(f"- {item}" for item in result.missing_sections)

    lines.extend([
        "",
        "ATS-risker",
    ])
    lines.extend(f"- {item}" for item in result.ats_risks)

    lines.extend([
        "",
        "Sektionspoäng",
    ])
    for section in result.section_scores:
        lines.append(f"- {section.section}: {section.score}/100")
        lines.extend(f"  - {finding}" for finding in section.findings)

    lines.extend([
        "",
        "Nyckelordsgap",
    ])
    for gap in result.keyword_gaps:
        status = "Finns i CV" if gap.present_in_cv else "Saknas i CV"
        lines.append(f"- {gap.keyword} | {gap.importance} | {status}")
        if gap.evidence:
            lines.append(f"  Evidence: {gap.evidence}")

    lines.extend([
        "",
        "Förslag på omskrivna bullets",
    ])
    for suggestion in result.bullet_suggestions:
        lines.append(f"- Original: {suggestion.original}")
        lines.append(f"  Förslag: {suggestion.suggestion}")
        lines.append(f"  Varför: {suggestion.reason}")

    lines.extend([
        "",
        "Rekommenderade nyckelord",
        ", ".join(result.recommended_keywords),
    ])

    return "\n".join(lines)


def select_target_job(saved_jobs: list[JobListing]) -> JobListing | None:
    if not saved_jobs:
        st.caption("Spara ett jobb för att kunna analysera CV:t mot en specifik roll.")
        return None

    saved_job_options = {
        f"{job.title} — {job.company}": job
        for job in saved_jobs
    }

    selected_job_label = st.selectbox(
        "Anpassa analysen mot sparat jobb",
        ["Generell CV-analys", *saved_job_options.keys()],
    )

    if selected_job_label == "Generell CV-analys":
        return None

    return saved_job_options[selected_job_label]


def render_resume_scan_result(result: ResumeScanResult) -> None:
    st.metric("ATS-score", f"{result.overall_score}/100")

    report_text = build_resume_scan_report(result)
    st.download_button(
        label="Ladda ner CV-rapport (.txt)",
        data=report_text,
        file_name="cv_scan_report.txt",
        mime="text/plain",
        use_container_width=True,
    )

    st.write("**Sammanfattning**")
    st.info(result.summary)

    col1, col2 = st.columns(2)

    with col1:
        st.write("**Styrkor**")
        if result.strengths:
            for item in result.strengths:
                st.write(f"- {item}")
        else:
            st.caption("Inga tydliga styrkor hittades.")

    with col2:
        st.write("**Svagheter**")
        if result.weaknesses:
            for item in result.weaknesses:
                st.write(f"- {item}")
        else:
            st.caption("Inga tydliga svagheter hittades.")

    st.write("**Saknade sektioner**")
    if result.missing_sections:
        for item in result.missing_sections:
            st.write(f"- {item}")
    else:
        st.caption("Inga uppenbara saknade sektioner hittades.")

    st.write("**ATS-risker**")
    if result.ats_risks:
        for item in result.ats_risks:
            st.write(f"- {item}")
    else:
        st.caption("Inga tydliga ATS-risker hittades.")

    st.write("**Sektionspoäng**")
    if result.section_scores:
        for section in result.section_scores:
            with st.expander(f"{section.section}: {section.score}/100"):
                for finding in section.findings:
                    st.write(f"- {finding}")
    else:
        st.caption("Ingen sektionsanalys returnerades.")

    st.write("**Nyckelordsgap**")
    if result.keyword_gaps:
        for gap in result.keyword_gaps:
            status = "Finns i CV" if gap.present_in_cv else "Saknas i CV"
            st.write(f"**{gap.keyword}** — {gap.importance} — {status}")
            if gap.evidence:
                st.caption(gap.evidence)
    else:
        st.caption("Inga tydliga nyckelordsgap hittades.")

    st.write("**Förslag på omskrivna bullets**")
    if result.bullet_suggestions:
        for suggestion in result.bullet_suggestions:
            with st.expander(suggestion.original):
                st.write("**Förslag**")
                st.write(suggestion.suggestion)
                st.write("**Varför**")
                st.write(suggestion.reason)
    else:
        st.caption("Inga bullet-förslag returnerades.")

    st.write("**Rekommenderade nyckelord**")
    if result.recommended_keywords:
        st.write(", ".join(result.recommended_keywords))
    else:
        st.caption("Inga rekommenderade nyckelord returnerades.")


def render_scanner_tab(final_cv_text: str) -> None:
    st.subheader("CV Scanner")
    st.caption(
        "Analysera ditt CV för ATS-risker, saknade sektioner, nyckelord och förbättringsförslag."
    )

    target_job = select_target_job(st.session_state.saved_jobs)
    current_scan_key = get_job_key(target_job) if target_job else "generic"

    if not final_cv_text.strip():
        st.info("Ladda upp ett CV eller klistra in CV-text för att kunna köra scannern.")
        return

    button_label = "Analysera CV mot valt jobb" if target_job else "Analysera CV"

    if st.button(button_label, type="primary", use_container_width=True):
        with st.spinner("Analyserar CV mot ATS-kriterier..."):
            scan_result = asyncio.run(scan_resume_with_ai(final_cv_text, target_job))

            if scan_result:
                st.session_state.resume_scan_result = scan_result
                st.session_state.last_scanned_cv_text = final_cv_text
                st.session_state.last_scanned_job_key = current_scan_key
            else:
                st.error(
                    "Kunde inte analysera CV:t just nu. Om du nyligen gjort flera sökningar kan Gemini-kvoten vara slut."
                )

    result = st.session_state.resume_scan_result

    if result and st.session_state.last_scanned_job_key != current_scan_key:
        result = None

    if result:
        render_resume_scan_result(result)