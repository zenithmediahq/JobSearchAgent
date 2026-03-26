import streamlit as st
from models import JobListing, ApplicationPack


def get_job_key(job: JobListing) -> str:
    title_key = (job.title or "").lower().strip()
    company_key = (job.company or "").lower().strip()
    return f"{title_key}|{company_key}"


def is_job_saved(job: JobListing) -> bool:
    job_key = get_job_key(job)
    return any(get_job_key(saved_job) == job_key for saved_job in st.session_state.saved_jobs)


def save_job(job: JobListing) -> None:
    if not is_job_saved(job):
        st.session_state.saved_jobs.append(job)


def remove_job(job: JobListing) -> None:
    job_key = get_job_key(job)
    st.session_state.saved_jobs = [
        saved_job
        for saved_job in st.session_state.saved_jobs
        if get_job_key(saved_job) != job_key
    ]


def update_job_status(job: JobListing, new_status: str) -> None:
    job_key = get_job_key(job)
    for saved_job in st.session_state.saved_jobs:
        if get_job_key(saved_job) == job_key:
            saved_job.status = new_status
            break


def save_application_pack(job: JobListing, pack: ApplicationPack) -> None:
    job_key = get_job_key(job)
    for saved_job in st.session_state.saved_jobs:
        if get_job_key(saved_job) == job_key:
            saved_job.short_motivation = pack.short_motivation
            saved_job.cover_letter = pack.cover_letter
            saved_job.cv_tailoring_tips = pack.cv_tailoring_tips
            break
