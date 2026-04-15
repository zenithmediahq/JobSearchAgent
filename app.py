import asyncio
import logging
import streamlit as st

from utils.export import build_fallback_job_link, jobs_to_csv
from models import JobListing
from services.cv_parser import extract_text_from_upload
from services.job_fetcher import run_search_workflow
from ui.scanner_tab import render_scanner_tab
from ui.results_tab import render_results_tab
from ui.saved_jobs_tab import render_saved_jobs_tab


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
    "last_scanned_cv_text": "",
    "last_scanned_job_key": "",
    "cv_text": "",
    "search_diagnostics": {},
    "resume_scan_result": None,
}

for key, value in DEFAULT_SESSION_VALUES.items():
    if key not in st.session_state:
        st.session_state[key] = value


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

with st.sidebar:
    st.header("Sökning")
    query = st.text_input("Jobbtitel eller sökord", value="IT support")
    location = st.text_input("Plats", value="Skåne")
    min_score = st.slider("Minsta matchning (%)", 0, 100, 40, 5)

    st.markdown("---")
    st.header("Filter")
    filter_remote = st.checkbox("Endast distans / hybrid")
    filter_fulltime = st.checkbox("Endast heltid")

    st.markdown("---")
    st.header("Jobbkällor")

    source_options = {
        "Platsbanken": st.checkbox("Platsbanken", value=True),
        "Indeed": st.checkbox("Indeed", value=True),
        "LinkedIn": st.checkbox("LinkedIn", value=False),
        "JobbSafari": st.checkbox("JobbSafari", value=False),
    }

    selected_sources = [
        source for source, enabled in source_options.items()
        if enabled
    ]


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

if final_cv_text != st.session_state.last_scanned_cv_text:
    st.session_state.resume_scan_result = None
    st.session_state.last_scanned_job_key = ""

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

tab_results, tab_saved, tab_scanner = st.tabs(["Resultat", "Sparade jobb", "CV Scanner"])

with tab_results:
    render_results_tab()

with tab_saved:
    render_saved_jobs_tab()

with tab_scanner:
    render_scanner_tab(final_cv_text)
