import asyncio
import logging
import streamlit as st

from utils.session_state import init_session_state
from utils.export import build_fallback_job_link, jobs_to_csv
from models import JobListing
from services.cv_parser import extract_text_from_upload
from services.job_fetcher import run_search_workflow
from ui.scanner_tab import render_scanner_tab
from ui.results_tab import render_results_tab
from ui.saved_jobs_tab import render_saved_jobs_tab
from ui.profile_input import render_profile_input
from ui.sidebar import render_sidebar
from ui.tailored_resume_tab import render_tailored_resume_tab


# -------------------------
# Inställningar
# -------------------------

st.set_page_config(page_title="AI Jobb-Agent", page_icon="💼", layout="wide")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -------------------------
# SESSION STATE RENDER
# -------------------------

init_session_state()


# -------------------------
# Hjälpfunktioner
# -------------------------


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

# -------------------------
# UI
# -------------------------

st.title("💼 AI Jobb-Agent")
st.caption("Ladda upp ditt CV, sök jobb och spara roller som passar din profil.")

query, location, min_score, filter_remote, filter_fulltime, selected_sources = render_sidebar()


final_cv_text = render_profile_input()

if final_cv_text != st.session_state.last_scanned_cv_text:
    st.session_state.resume_scan_result = None
    st.session_state.last_scanned_job_key = ""

if final_cv_text != st.session_state.last_tailored_cv_text:
    st.session_state.tailored_resume_result = None
    st.session_state.last_tailored_job_key = ""


search_col1, search_col2 = st.columns([2, 1])

with search_col1:
    start_search = st.button("Starta AI-sökning", type="primary", use_container_width=True)

with search_col2:
    st.metric("Min score", f"{min_score}%")

if start_search:
    if not final_cv_text.strip():
        st.warning("Du behöver ladda upp ett CV eller klistra in CV-text först.")
    elif not selected_sources:
        st.warning("Välj minst en jobbsajt att söka i.")
    else:
        with st.spinner("Söker källor, läser annonser och poängsätter matchning..."):

            try:
                search_result = asyncio.run(
                    run_search_workflow(
                        query,
                        location,
                        final_cv_text,
                        min_score,
                        selected_sources,
                    )
                )

                all_found_jobs, diagnostics = search_result


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

tab_results, tab_saved, tab_scanner, tab_builder = st.tabs(
    ["Resultat", "Sparade jobb", "CV Scanner", "CV Builder"]

)

with tab_results:
    render_results_tab()

with tab_saved:
    render_saved_jobs_tab()

with tab_scanner:
    render_scanner_tab(final_cv_text)

with tab_builder:
    render_tailored_resume_tab(final_cv_text)
