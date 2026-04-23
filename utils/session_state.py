import streamlit as st


DEFAULT_SESSION_VALUES = {
    "search_results": [],
    "saved_jobs": [],
    "search_ran": False,
    "last_query": "",
    "last_location": "",
    "last_min_score": 0,
    "last_scanned_cv_text": "",
    "last_scanned_job_key": "",
    "tailored_resume_result": None,
    "last_tailored_cv_text": "",
    "last_tailored_job_key": "",

    "interview_question_set": None,
    "interview_feedback_set": None,
    "last_interview_cv_text": "",
    "last_interview_job_key": "",


    "cv_text": "",
    "search_diagnostics": {},
    "resume_scan_result": None,
}


def init_session_state() -> None:
    for key, value in DEFAULT_SESSION_VALUES.items():
        if key not in st.session_state:
            st.session_state[key] = value
