import asyncio

import streamlit as st

from models import JobListing
from services.application_pack import generate_application_pack
from ui.results_tab import (
    get_score_emoji,
    get_job_link,
    render_job_meta,
    render_match_analysis,
    sort_jobs,
)
from utils.export import build_application_pack_text, jobs_to_csv
from utils.job_state import (
    get_job_key,
    remove_job,
    save_application_pack,
    update_job_status,
)


def render_saved_job_card(job: JobListing) -> None:
    score = job.match_score or 0
    score_emoji = get_score_emoji(score)
    link, link_label = get_job_link(job)
    job_key = get_job_key(job)

    title = job.title or "Okänd titel"
    company = job.company or "Okänt företag"

    with st.container(border=True):
        st.markdown(f"### {score_emoji} {title}")
        st.write(f"**{company}**")

        render_job_meta(job)

        status_options = ["Ej ansökt", "Ansökt", "Intervju", "Avslag"]
        current_status = job.status if job.status in status_options else "Ej ansökt"

        new_status = st.selectbox(
            "Status",
            status_options,
            index=status_options.index(current_status),
            key=f"status_{job_key}",
        )

        if new_status != current_status:
            update_job_status(job, new_status)
            st.rerun()

        col1, col2 = st.columns(2)

        with col1:
            if st.button(
                "Generera ansökningspaket",
                key=f"pack_{job_key}",
                use_container_width=True,
            ):
                with st.spinner("Genererar ansökningspaket..."):
                    pack = asyncio.run(generate_application_pack(job, st.session_state.cv_text))
                    if pack:
                        save_application_pack(job, pack)
                        st.rerun()
                    else:
                        st.error("Kunde inte generera ansökningspaket.")

        with col2:
            if st.button(
                "Ta bort",
                key=f"remove_{job_key}",
                use_container_width=True,
            ):
                remove_job(job)
                st.rerun()

        st.link_button(link_label, link, use_container_width=True)

        with st.expander("Visa detaljer"):
            render_match_analysis(job)

            if job.short_motivation or job.cover_letter:
                st.caption("Markera och kopiera texten direkt härifrån.")

            if job.short_motivation:
                st.write("**Kort motivation**")
                st.text_area(
                    "Kort motivation",
                    value=job.short_motivation,
                    height=100,
                    key=f"motivation_{job_key}",
                    label_visibility="collapsed",
                )

            if job.cover_letter:
                st.write("**Personligt brev**")
                st.text_area(
                    "Personligt brev",
                    value=job.cover_letter,
                    height=220,
                    key=f"cover_letter_{job_key}",
                    label_visibility="collapsed",
                )

            if job.cv_tailoring_tips:
                st.write("**CV-anpassning**")
                for tip in job.cv_tailoring_tips:
                    st.write(f"- {tip}")

            if job.short_motivation or job.cover_letter or job.cv_tailoring_tips:
                pack_text = build_application_pack_text(job)
                safe_company = (job.company or "company").replace(" ", "_")
                safe_title = (job.title or "job").replace(" ", "_")

                st.download_button(
                    label="Ladda ner ansökningspaket (.txt)",
                    data=pack_text,
                    file_name=f"application_pack_{safe_company}_{safe_title}.txt",
                    mime="text/plain",
                    key=f"download_pack_{job_key}",
                    use_container_width=True,
                )


def render_saved_jobs_tab() -> None:
    st.subheader("Sparade jobb")

    if not st.session_state.saved_jobs:
        st.caption("Inga sparade jobb ännu.")
        return

    saved_sort_by = st.selectbox(
        "Sortera sparade jobb",
        ["Högst matchning", "Lägst matchning", "Företag A-Ö", "Titel A-Ö"],
        key="saved_sort",
    )

    sorted_saved_jobs = sort_jobs(st.session_state.saved_jobs, saved_sort_by)

    saved_csv_data = jobs_to_csv(sorted_saved_jobs)
    st.download_button(
        label="Ladda ner sparade jobb som CSV",
        data=saved_csv_data,
        file_name="saved_jobs.csv",
        mime="text/csv",
        use_container_width=True,
    )

    for job in sorted_saved_jobs:
        render_saved_job_card(job)