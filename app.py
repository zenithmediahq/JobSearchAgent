import asyncio
import logging
import streamlit as st

from utils.export import build_fallback_job_link, jobs_to_csv, build_application_pack_text
from models import JobListing
from services.cv_parser import extract_text_from_upload
from services.application_pack import generate_application_pack
from services.job_fetcher import run_search_workflow
from services.resume_scanner import scan_resume_with_ai
from utils.job_state import (
    get_job_key,
    is_job_saved,
    save_job,
    remove_job,
    update_job_status,
    save_application_pack,
)

# -------------------------
# Inställningar
# -------------------------

st.set_page_config(page_title="AI Jobb-Agent", page_icon="💼", layout="wide")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -------------------------
# SESSION STATE
# -------------------------

DEFAULT_SESSION_VALUES = {
    "search_results": [],
    "saved_jobs": [],
    "search_ran": False,
    "last_query": "",
    "last_location": "",
    "last_min_score": 0,
    "cv_text": "",
    "search_diagnostics": {},
    "resume_scan_results": None,
}

for key, value in DEFAULT_SESSION_VALUES.items():
    if key not in st.session_state:
        st.session_state[key] = value


# -------------------------
# Hjälpfunktioner
# -------------------------

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


def render_job_meta(job: JobListing):
    score = job.match_score or 0
    badges = build_badges(job)

    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Plats:** {job.location or 'Ej angivet'}")
    with col2:
        st.write(f"**Matchning:** {score}%")

    if badges:
        st.caption(" • ".join(badges))


def render_match_analysis(job: JobListing):
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


def apply_ui_filters(
    jobs: list[JobListing],
    filter_remote: bool,
    filter_fulltime: bool
) -> list[JobListing]:
    filtered_jobs = []

    for job in jobs:
        if filter_remote:
            wm = str(job.work_mode or "").lower()
            if "distans" not in wm and "hybrid" not in wm and "remote" not in wm:
                continue

        if filter_fulltime:
            et = str(job.employment_type or "").lower()
            if "heltid" not in et and "full-time" not in et and "full time" not in et:
                continue

        filtered_jobs.append(job)

    return filtered_jobs


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


def render_search_diagnostics(diagnostics: dict, visible_results_count: int):
    with st.expander("Visa sökdiagnostik"):
        for source in diagnostics.get("sources", []):
            status = "hämtad" if source.get("fetched") else "misslyckades / tomt svar"
            st.write(
                f"**{source['platform']}** — {status}, extraherade jobb: {source['jobs_extracted']}"
            )

        st.write(f"**Före dubblettfilter:** {diagnostics.get('before_dedup', 0)}")
        st.write(f"**Efter dubblettfilter:** {diagnostics.get('after_dedup', 0)}")
        st.write(f"**Efter AI-scorefilter:** {diagnostics.get('after_score_filter', 0)}")
        st.write(f"**Efter valda UI-filter:** {visible_results_count}")


def render_search_result_card(job: JobListing):
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
                    use_container_width=True
                ):
                    remove_job(job)
                    st.rerun()
            else:
                if st.button(
                    "Spara jobb",
                    key=f"save_{job_key}",
                    use_container_width=True
                ):
                    save_job(job)
                    st.rerun()

        with col2:
            st.link_button(link_label, link, use_container_width=True)

        with st.expander("Visa matchningsanalys"):
            render_match_analysis(job)


def render_saved_job_card(job: JobListing):
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
                use_container_width=True
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
                use_container_width=True
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


# -------------------------
# UI
# -------------------------

st.title("💼 AI Jobb-Agent")
st.caption("Ladda upp ditt CV, sök jobb och spara roller som passar din profil.")

with st.sidebar:
    st.header("Sökning")
    query = st.text_input("Jobbtitel eller sökord", value="IT support")
    location = st.text_input("Plats", value="Skåne")
    min_score = st.slider("Minsta matchning (%)", 0, 100, 40, 5)

    st.markdown("---")
    st.header("Filter")
    filter_remote = st.checkbox("Endast distans / hybrid")
    filter_fulltime = st.checkbox("Endast heltid")

st.subheader("Din profil")

uploaded_file = st.file_uploader(
    "Ladda upp CV (PDF, DOCX eller TXT)",
    type=["pdf", "docx", "txt"],
)

cv_text_input = st.text_area(
    "Eller klistra in CV-text manuellt",
    height=140,
    placeholder="Klistra in din CV-text här...",
)

final_cv_text = ""
if uploaded_file is not None:
    final_cv_text = extract_text_from_upload(uploaded_file)
    st.success(f"Filen '{uploaded_file.name}' är inläst.")
elif cv_text_input.strip():
    final_cv_text = cv_text_input.strip()

search_col1, search_col2 = st.columns([2, 1])

with search_col1:
    start_search = st.button("Starta AI-sökning", type="primary", use_container_width=True)

with search_col2:
    st.metric("Min score", f"{min_score}%")

if start_search:
    if not final_cv_text.strip():
        st.warning("Du behöver ladda upp ett CV eller klistra in CV-text först.")
    else:
        with st.spinner("Söker källor, läser annonser och poängsätter matchning..."):
            try:
                all_found_jobs, diagnostics = asyncio.run(
                    run_search_workflow(query, location, final_cv_text, min_score)
                )

                filtered_jobs = apply_ui_filters(
                    all_found_jobs,
                    filter_remote=filter_remote,
                    filter_fulltime=filter_fulltime,
                )

                st.session_state.search_results = filtered_jobs
                st.session_state.search_ran = True
                st.session_state.last_query = query
                st.session_state.last_location = location
                st.session_state.last_min_score = min_score
                st.session_state.cv_text = final_cv_text
                st.session_state.search_diagnostics = diagnostics

            except Exception as e:
                st.error(f"Ett fel uppstod: {e}")

tab_results, tab_saved = st.tabs(["Resultat", "Sparade jobb"])

with tab_results:
    st.subheader("Resultat")

    if st.session_state.search_ran:
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
        else:
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
    else:
        st.caption("Ingen sökning har körts ännu.")

with tab_saved:
    st.subheader("Sparade jobb")

    if st.session_state.saved_jobs:
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
    else:
        st.caption("Inga sparade jobb ännu.")
