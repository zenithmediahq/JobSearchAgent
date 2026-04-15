import streamlit as st

from models import JobListing
from utils.export import build_fallback_job_link, jobs_to_csv
from utils.job_state import (
    get_job_key,
    is_job_saved,
    save_job,
    remove_job,
)


def get_score_emoji(score: int) -> str:
    if score >= 80:
        return "🟢"
    if score >= 60:
        return "🟡"
    return "🔴"


def get_job_link(job: JobListing) -> tuple[str, str]:
    link = job.application_url
    if not link or str(link).lower() == "none":
        return build_fallback_job_link(job), "🔍 Sök upp annonsen"
    return link, "🔗 Gå till ansökan"


def build_badges(job: JobListing) -> list[str]:
    badges = []
    if job.work_mode and str(job.work_mode).lower() != "none":
        badges.append(f"🏠 {job.work_mode}")
    if job.employment_type and str(job.employment_type).lower() != "none":
        badges.append(f"⏱️ {job.employment_type}")
    if job.source_platform and str(job.source_platform).lower() != "none":
        badges.append(f"🌐 {job.source_platform}")
    return badges


def render_job_meta(job: JobListing) -> None:
    score = job.match_score or 0
    badges = build_badges(job)

    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Plats:** {job.location or 'Ej angivet'}")
    with col2:
        st.write(f"**Matchning:** {score}%")

    if badges:
        st.caption(" • ".join(badges))


def render_match_analysis(job: JobListing) -> None:
    if job.match_strengths:
        st.write("**Styrkor**")
        for item in job.match_strengths:
            st.write(f"- {item}")

    if job.match_gaps:
        st.write("**Saknas / svagheter**")
        for item in job.match_gaps:
            st.write(f"- {item}")

    if job.match_recommendation:
        st.info(job.match_recommendation)


def sort_jobs(jobs: list[JobListing], sort_by: str) -> list[JobListing]:
    if sort_by == "Högst matchning":
        return sorted(jobs, key=lambda job: job.match_score or 0, reverse=True)
    if sort_by == "Lägst matchning":
        return sorted(jobs, key=lambda job: job.match_score or 0)
    if sort_by == "Företag A-Ö":
        return sorted(jobs, key=lambda job: (job.company or "").lower())
    if sort_by == "Titel A-Ö":
        return sorted(jobs, key=lambda job: (job.title or "").lower())
    return jobs


def render_search_diagnostics(diagnostics: dict, visible_results_count: int) -> None:
    with st.expander("Visa sökdiagnostik"):
        for source in diagnostics.get("sources", []):
            status = "hämtad" if source.get("fetched") else "misslyckades / tomt svar"
            st.write(
                f"**{source['platform']}** — {status}, extraherade jobb: {source['jobs_extracted']}"
            )

            if source.get("url"):
                st.caption(source["url"])

            st.write(f"Markdown-tecken: {source.get('markdown_chars', 0)}")
            st.write(f"Efter AI-scorefilter: {source.get('after_score_filter', 0)}")

        st.write(f"**Före dubblettfilter:** {diagnostics.get('before_dedup', 0)}")
        st.write(f"**Efter dubblettfilter:** {diagnostics.get('after_dedup', 0)}")
        st.write(f"**Efter AI-scorefilter:** {diagnostics.get('after_score_filter', 0)}")
        st.write(f"**Efter valda UI-filter:** {visible_results_count}")


def render_search_result_card(job: JobListing) -> None:
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

        if job.match_recommendation:
            st.caption(f"Bedömning: {job.match_recommendation}")

        col1, col2 = st.columns(2)

        with col1:
            if is_job_saved(job):
                st.success("Sparat")
                if st.button(
                    "Ta bort från sparade",
                    key=f"unsave_{job_key}",
                    use_container_width=True,
                ):
                    remove_job(job)
                    st.rerun()
            else:
                if st.button(
                    "Spara jobb",
                    key=f"save_{job_key}",
                    use_container_width=True,
                ):
                    save_job(job)
                    st.rerun()

        with col2:
            st.link_button(link_label, link, use_container_width=True)

        with st.expander("Visa matchningsanalys"):
            render_match_analysis(job)


def render_results_tab() -> None:
    st.subheader("Resultat")

    if not st.session_state.search_ran:
        st.caption("Ingen sökning har körts ännu.")
        return

    results = st.session_state.search_results
    diagnostics = st.session_state.search_diagnostics

    info1, info2, info3 = st.columns(3)
    with info1:
        st.info(f"**Visade jobb:** {len(results)}")
    with info2:
        st.info(f"**Sökord:** {st.session_state.last_query or '-'}")
    with info3:
        st.info(f"**Plats:** {st.session_state.last_location or '-'}")

    st.caption(
        f"Senaste sökning: {st.session_state.last_query} i {st.session_state.last_location} "
        f"• Min score: {st.session_state.last_min_score}%"
    )

    render_search_diagnostics(diagnostics, len(results))

    if not results:
        after_score_filter = diagnostics.get("after_score_filter", 0)

        if after_score_filter > 0:
            st.info(
                "Det finns jobb efter AI-filtreringen, men inga klarade dina valda UI-filter. "
                "Testa att stänga av distans/hybrid eller heltid-filtret."
            )
        else:
            st.info(
                "Inga jobb klarade matchningskravet. "
                "Testa lägre min score eller bredare sökord."
            )
        return

    sort_by = st.selectbox(
        "Sortera resultat",
        ["Högst matchning", "Lägst matchning", "Företag A-Ö", "Titel A-Ö"],
    )

    sorted_results = sort_jobs(results, sort_by)

    csv_data = jobs_to_csv(sorted_results)
    st.download_button(
        label="Ladda ner resultat som CSV",
        data=csv_data,
        file_name="job_results.csv",
        mime="text/csv",
        use_container_width=True,
    )

    for job in sorted_results:
        render_search_result_card(job)