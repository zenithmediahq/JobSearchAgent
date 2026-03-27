import streamlit as st
import asyncio
import logging

from utils.export import build_fallback_job_link, jobs_to_csv, build_application_pack_text
from models import JobListing
from services.cv_parser import extract_text_from_upload
from services.application_pack import generate_application_pack
from services.job_fetcher import run_search_workflow
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

LINKUP_API_URL = "https://api.linkup.so/v1/fetch"
AI_MODEL = "gemini-2.5-flash"
MAX_CONTENT_CHARS = 50000


# -------------------------
# SESSION STATE
# -------------------------

if "search_results" not in st.session_state:
    st.session_state.search_results = []

if "saved_jobs" not in st.session_state:
    st.session_state.saved_jobs = []

if "search_ran" not in st.session_state:
    st.session_state.search_ran = False

if "last_query" not in st.session_state:
    st.session_state.last_query = ""

if "last_location" not in st.session_state:
    st.session_state.last_location = ""

if "last_min_score" not in st.session_state:
    st.session_state.last_min_score = 0

if "cv_text" not in st.session_state:
    st.session_state.cv_text = ""

if "search_diagnostics" not in st.session_state:
    st.session_state.search_diagnostics = {}

# -------------------------
# WEBBGRÄNSSNITT (UI)
# -------------------------

st.title("💼 Din Personliga AI-Rekryterare")
st.markdown(
    "Ladda upp ditt CV och fyll i vad du letar efter. AI:n skannar marknaden, "
    "filtrerar bort bruset och presenterar endast jobben som passar dig."
)

# --- SIDOPANEL: INSTÄLLNINGAR & FILTER ---

with st.sidebar:
    st.header("🔍 Sökinställningar")
    query = st.text_input("Jobbtitel / Sökord", value="IT support")
    location = st.text_input("Plats", value="Skåne")
    min_score = st.slider("Lägsta AI-matchning (%)", 0, 100, 40, 5)

    st.markdown("---")
    st.header("⚙️ Smarta Filter")
    filter_remote = st.checkbox("🏠 Visa endast Distans/Hybrid")
    filter_fulltime = st.checkbox("⏱️ Visa endast Heltid")

# --- HUVUDYTA: LADD UPP CV ---

st.subheader("📄 Ladda upp din profil")
uploaded_file = st.file_uploader(
    "Dra och släpp ditt CV här (PDF, DOCX eller TXT)",
    type=["pdf", "docx", "txt"],
)
cv_text_input = st.text_area("...eller klistra in din text manuellt:", height=100)

# Bestäm vilken text vi använder
final_cv_text = ""
if uploaded_file is not None:
    final_cv_text = extract_text_from_upload(uploaded_file)
    st.success(f"✅ Filen '{uploaded_file.name}' inläst och redo!")
elif cv_text_input.strip():
    final_cv_text = cv_text_input.strip()

# --- SÖKKNAPP ---

if st.button("🚀 Starta AI-sökning", type="primary", use_container_width=True):
    if not final_cv_text.strip():
        st.warning("⚠️ Du måste antingen ladda upp ditt CV eller klistra in texten först!")
    else:
        with st.spinner("🤖 Agenten söker av nätet och läser annonser... (Tar ca 30-60 sek)"):
            try:
                all_found_jobs, diagnostics = asyncio.run(
                    run_search_workflow(query, location, final_cv_text, min_score)
                )

                # --- APPLICERA EXTRA FILTER (Distans & Heltid) ---
                
                filtered_jobs = []
                for job in all_found_jobs:
                    if filter_remote:
                        wm = str(job.work_mode or "").lower()
                        if "distans" not in wm and "hybrid" not in wm and "remote" not in wm:
                            continue

                    if filter_fulltime:
                        et = str(job.employment_type or "").lower()
                        if "heltid" not in et and "full-time" not in et and "full time" not in et:
                            continue

                    filtered_jobs.append(job)

                st.session_state.search_results = filtered_jobs
                st.session_state.search_ran = True
                st.session_state.last_query = query
                st.session_state.last_location = location
                st.session_state.last_min_score = min_score
                st.session_state.cv_text = final_cv_text
                st.session_state.search_diagnostics = diagnostics

            except Exception as e:
                st.error(f"Ett fel uppstod: {e}")


# --- VISNING AV SPARADE RESULTAT ---

st.subheader("📋 Resultat")
if st.session_state.search_ran:
    saved_results = st.session_state.search_results
    diagnostics = st.session_state.search_diagnostics

    with st.expander("🔎 Sökdiagnostik"):
        for source in diagnostics.get("sources", []):
            status = "hämtad" if source.get("fetched") else "fetch misslyckades / tomt svar"
            st.write(
                f"**{source['platform']}** — {status}, extraherade jobb: {source['jobs_extracted']}"
            )

        st.write(f"**Före dubblettfilter:** {diagnostics.get('before_dedup', 0)}")
        st.write(f"**Efter dubblettfilter:** {diagnostics.get('after_dedup', 0)}")
        st.write(f"**Efter AI-scorefilter:** {diagnostics.get('after_score_filter', 0)}")
        st.write(f"**Efter valda UI-filter:** {len(saved_results)}")

    if not saved_results:
        st.info(
            "🤷‍♂️ Hittade inga jobb som klarade både matchningskravet och dina valda filter. "
            "Prova att ändra filtren!"
        )
    else:
        st.success(f"✅ Sökning klar! Hittade {len(saved_results)} unika jobb som passar dina krav.")

        st.caption(
            f"Senaste sökning: {st.session_state.last_query} i {st.session_state.last_location} "
            f"(min score: {st.session_state.last_min_score}%)"
        )

        csv_data = jobs_to_csv(saved_results)
        st.download_button(
            label="📥 Ladda ner resultat som CSV",
            data=csv_data,
            file_name="job_results.csv",
            mime="text/csv",
            use_container_width=True,
        )

        for job in saved_results:
            score = job.match_score or 0
            color = "🟢" if score >= 80 else "🟡" if score >= 60 else "🔴"

            link = job.application_url
            if not link or str(link).lower() == "none":
                link = build_fallback_job_link(job)
                link_label = "🔍 Googla jobbet (Länk saknas)"
            else:
                link_label = "🔗 Gå till ansökan"

            badges = []
            if job.work_mode and job.work_mode.lower() != "none":
                badges.append(f"🏠 {job.work_mode}")
            if job.employment_type and job.employment_type.lower() != "none":
                badges.append(f"⏱️ {job.employment_type}")
            badge_str = " | ".join(badges)

            with st.expander(f"{color} [{score}%] {job.title} @ {job.company}"):
                c1, c2 = st.columns(2)
                c1.write(f"**📍 Plats:** {job.location}")
                c2.write(f"**🌐 Källa:** {job.source_platform}")

                if is_job_saved(job):
                    st.success("✅ Sparat jobb")
                    if st.button(
                        f"🗑️ Ta bort från sparade: {job.title} @ {job.company}",
                        key=f"unsave_{get_job_key(job)}"
                    ):
                        remove_job(job)
                        st.rerun()
                else:
                    if st.button(
                        f"⭐ Spara jobb: {job.title} @ {job.company}",
                        key=f"save_{get_job_key(job)}"
                    ):
                        save_job(job)
                        st.rerun()

                if badge_str:
                    st.write(f"**Upplägg:** {badge_str}")

                if job.match_strengths:
                    st.write("**✅ Styrkor:**")
                    for item in job.match_strengths:
                        st.write(f"- {item}")

                if job.match_gaps:
                    st.write("**⚠️ Saknas / Svagheter:**")
                    for item in job.match_gaps:
                        st.write(f"- {item}")

                if job.match_recommendation:
                    st.info(f"**💡 Rekommendation:** {job.match_recommendation}")

                st.markdown(f"[{link_label}]({link})")
                
# --- SPARADE JOBB ---

if st.session_state.saved_jobs:
    st.subheader("⭐ Sparade jobb")

    saved_csv_data = jobs_to_csv(st.session_state.saved_jobs)
    st.download_button(
        label="📥 Ladda ner sparade jobb som CSV",
        data=saved_csv_data,
        file_name="saved_jobs.csv",
        mime="text/csv",
        use_container_width=True,
    )

    for job in st.session_state.saved_jobs:
        score = job.match_score or 0
        color = "🟢" if score >= 80 else "🟡" if score >= 60 else "🔴"

        link = job.application_url
        if not link or str(link).lower() == "none":
            link = build_fallback_job_link(job)
            link_label = "🔍 Googla jobbet (Länk saknas)"
        else:
            link_label = "🔗 Gå till ansökan"

        badges = []
        if job.work_mode and job.work_mode.lower() != "none":
            badges.append(f"🏠 {job.work_mode}")
        if job.employment_type and job.employment_type.lower() != "none":
            badges.append(f"⏱️ {job.employment_type}")
        badge_str = " | ".join(badges)

        with st.expander(f"{color} [{score}%] {job.title} @ {job.company}"):
            c1, c2 = st.columns(2)
            c1.write(f"**📍 Plats:** {job.location}")
            c2.write(f"**🌐 Källa:** {job.source_platform}")

            status_options = ["Ej ansökt", "Ansökt", "Intervju", "Avslag"]
            current_status = job.status if job.status in status_options else "Ej ansökt"

            new_status = st.selectbox(
                "Status",
                status_options,
                index=status_options.index(current_status),
                key=f"status_{get_job_key(job)}"
            )

            if new_status != current_status:
                update_job_status(job, new_status)
                st.rerun()

            if st.button(
                f"✍️ Generera ansökningspaket: {job.title} @ {job.company}",
                key=f"pack_{get_job_key(job)}"
            ):
                with st.spinner("Genererar ansökningspaket..."):
                    pack = asyncio.run(generate_application_pack(job, st.session_state.cv_text))
                    if pack:
                        save_application_pack(job, pack)
                        st.rerun()
                    else:
                        st.error("Kunde inte generera ansökningspaket.")

            if st.button(
                f"🗑️ Ta bort: {job.title} @ {job.company}",
                key=f"remove_{get_job_key(job)}"
            ):
                remove_job(job)
                st.rerun()

            if badge_str:
                st.write(f"**Upplägg:** {badge_str}")

            if job.match_strengths:
                st.write("**✅ Styrkor:**")
                for item in job.match_strengths:
                    st.write(f"- {item}")

            if job.match_gaps:
                st.write("**⚠️ Saknas / Svagheter:**")
                for item in job.match_gaps:
                    st.write(f"- {item}")

            if job.match_recommendation:
                st.info(f"**💡 Rekommendation:** {job.match_recommendation}")

            if job.short_motivation or job.cover_letter:
                st.caption("Markera och kopiera texten direkt härifrån.")

            if job.short_motivation:
                st.write("**📝 Kort motivation:**")
                st.text_area(
                    "Kort motivation",
                    value=job.short_motivation,
                    height=100,
                    key=f"motivation_{get_job_key(job)}"
                )

            if job.cover_letter:
                st.write("**📄 Personligt brev:**")
                st.text_area(
                    "Personligt brev",
                    value=job.cover_letter,
                    height=220,
                    key=f"cover_letter_{get_job_key(job)}"
                )

            if job.cv_tailoring_tips:
                st.write("**🎯 CV-anpassning:**")
                for tip in job.cv_tailoring_tips:
                    st.write(f"- {tip}")

            if job.short_motivation or job.cover_letter or job.cv_tailoring_tips:
                pack_text = build_application_pack_text(job)
                safe_company = (job.company or "company").replace(" ", "_")
                safe_title = (job.title or "job").replace(" ", "_")

                st.download_button(
                    label="📄 Ladda ner ansökningspaket (.txt)",
                    data=pack_text,
                    file_name=f"application_pack_{safe_company}_{safe_title}.txt",
                    mime="text/plain",
                    key=f"download_pack_{get_job_key(job)}"
                )

            st.markdown(f"[{link_label}]({link})")
else:
    st.caption("Inga sparade jobb ännu.")
