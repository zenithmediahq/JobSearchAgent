import streamlit as st
import asyncio
import logging
import csv
import urllib.parse
import httpx
from pydantic import BaseModel
from openai import AsyncOpenAI
from io import BytesIO, StringIO
import fitz  # pymupdf
from docx import Document  # python-docx

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
# Datamodeller
# -------------------------

class JobListing(BaseModel):
    title: str
    company: str
    location: str
    description: str
    work_mode: str | None = None
    employment_type: str | None = None
    application_url: str | None = None
    source_platform: str | None = None
    match_score: int | None = None
    match_strengths: list[str] | None = None
    match_gaps: list[str] | None = None
    match_recommendation: str | None = None
    status: str = "Ej ansökt"
    short_motivation: str | None = None
    cover_letter: str | None = None
    cv_tailoring_tips: list[str] | None = None


class JobListings(BaseModel):
    jobs: list[JobListing]
    total_count: int


class ScoredJob(BaseModel):
    index: int
    score: int
    strengths: list[str]
    gaps: list[str]
    recommendation: str


class ScoringResult(BaseModel):
    scored_jobs: list[ScoredJob]

class ApplicationPack(BaseModel):
    short_motivation: str
    cover_letter: str
    cv_tailoring_tips: list[str]


# -------------------------
# Hjälpfunktion för att läsa CV-filer
# -------------------------

def extract_text_from_upload(uploaded_file) -> str:
    """Extraherar text från PDF, DOCX eller TXT-filer."""
    file_bytes = uploaded_file.read()
    filename = uploaded_file.name.lower()

    if filename.endswith(".pdf"):
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        return "\n".join(page.get_text() for page in doc).strip()

    if filename.endswith(".docx"):
        doc = Document(BytesIO(file_bytes))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    return file_bytes.decode("utf-8", errors="replace")

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

# -------------------------
# AI och Sök-funktioner
# -------------------------

def get_api_key(secret_name: str) -> str:
    try:
        return st.secrets[secret_name]
    except Exception:
        st.error(f"Saknar API-nyckel: {secret_name}")
        st.stop()


def get_ai_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=get_api_key("GEMINI_API_KEY"),
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )


async def fetch_webpage(url: str) -> str:
    headers = {
        "Authorization": f"Bearer {get_api_key('LINKUP_API_KEY')}",
        "Content-Type": "application/json",
    }
    payload = {
        "url": url,
        "includeRawHtml": False,
        "renderJs": True,
        "extractImages": False,
    }

    async with httpx.AsyncClient(timeout=120) as client:
        try:
            response = await client.post(LINKUP_API_URL, headers=headers, json=payload)
            response.raise_for_status()
            return response.json().get("markdown", "")
        except Exception as e:
            logger.warning(f"Kunde inte läsa {url}: {e}")
            return ""


async def extract_jobs_with_ai(markdown: str, url: str) -> list[JobListing]:
    if not markdown:
        return []

    markdown = markdown[:MAX_CONTENT_CHARS]
    client = get_ai_client()

    try:
        response = await client.beta.chat.completions.parse(
            model=AI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extrahera alla jobbannonser. Identifiera titel, företag, plats, länk, "
                        "arbetsform (distans/hybrid/på plats), anställningstyp (heltid/deltid) "
                        "och beskrivning."
                    ),
                },
                {"role": "user", "content": f"URL: {url}\n\nInnehåll:\n{markdown}"},
            ],
            response_format=JobListings,
        )
        return response.choices[0].message.parsed.jobs
    except Exception as e:
        logger.error(f"AI Extraktionsfel: {e}")
        return []


async def score_jobs_with_ai(jobs: list[JobListing], skills: str) -> list[JobListing]:
    if not jobs:
        return []

    job_summaries = [
        f"[{i}] {j.title} @ {j.company} | {j.description[:2000]}"
        for i, j in enumerate(jobs)
    ]

    client = get_ai_client()

    try:
        response = await client.beta.chat.completions.parse(
            model=AI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Du är en stenhård rekryterare. "
                        "Betygsätt varje jobb 0-100 baserat på hur väl kandidatens CV matchar kraven. "
                        "Returnera för varje jobb:\n"
                        "- score: ett heltal 0-100\n"
                        "- strengths: 2 till 4 korta styrkor på svenska\n"
                        "- gaps: 2 till 4 korta brister eller saknade krav på svenska\n"
                        "- recommendation: 1 kort rekommendation på svenska\n\n"
                        "Var kritisk. Hitta inte på erfarenhet som inte finns i CV:t. "
                        "Håll allt kort, tydligt och konkret."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Kandidatens CV:\n{skills}\n\n"
                        f"Jobbannonser:\n{chr(10).join(job_summaries)}"
                    ),
                },
            ],
            response_format=ScoringResult,
        )

        score_map = {s.index: s for s in response.choices[0].message.parsed.scored_jobs}

        for i, job in enumerate(jobs):
            if i in score_map:
                scored = score_map[i]
                job.match_score = scored.score
                job.match_strengths = scored.strengths
                job.match_gaps = scored.gaps
                job.match_recommendation = scored.recommendation

        jobs.sort(key=lambda j: j.match_score or 0, reverse=True)

    except Exception as e:
        logger.error(f"Scoring fel: {e}")

    return jobs

async def generate_application_pack(job: JobListing, cv_text: str) -> ApplicationPack | None:
    client = get_ai_client()

    try:
        response = await client.beta.chat.completions.parse(
            model=AI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Du hjälper kandidaten att skriva ett ansökningspaket på svenska. "
                        "Du får kandidatens riktiga CV och en jobbannons. "
                        "Du får aldrig hitta på erfarenhet, utbildning, certifikat eller ansvar som inte finns i CV:t. "
                        "Skriv tydligt, konkret och professionellt. Undvik överdrivet språk.\n\n"
                        "Returnera:\n"
                        "- short_motivation: 2 till 4 meningar, kort och användbar för ansökningsformulär\n"
                        "- cover_letter: ett kort personligt brev på svenska\n"
                        "- cv_tailoring_tips: 3 till 6 konkreta tips om vad kandidaten bör lyfta fram eller justera i sitt CV för detta jobb"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Kandidatens CV:\n{cv_text}\n\n"
                        f"Jobb:\n"
                        f"Titel: {job.title}\n"
                        f"Företag: {job.company}\n"
                        f"Plats: {job.location}\n"
                        f"Arbetsform: {job.work_mode}\n"
                        f"Anställningstyp: {job.employment_type}\n"
                        f"Beskrivning:\n{job.description[:4000]}"
                    ),
                },
            ],
            response_format=ApplicationPack,
        )
        return response.choices[0].message.parsed
    except Exception as e:
        logger.error(f"Application pack fel: {e}")
        return None


def build_fallback_job_link(job: JobListing) -> str:
    company = urllib.parse.quote(job.company or "")
    title = urllib.parse.quote(job.title or "")
    return f"https://www.google.com/search?q={company}+{title}+jobb"


def jobs_to_csv(jobs: list[JobListing]) -> str:
    """Konverterar jobblistan till CSV-format med BOM för bättre Excel-stöd."""
    output = StringIO()
    output.write("\ufeff")  # UTF-8 BOM för Excel

    writer = csv.writer(output)
    writer.writerow([
        "Title",
        "Company",
        "Location",
        "Work Mode",
        "Employment Type",
        "Match Score",
        "Strengths",
        "Gaps",
        "Recommendation",
        "Status",
        "Application Link",
        "Source",
    ])

    for job in jobs:
        writer.writerow([
            job.title or "",
            job.company or "",
            job.location or "",
            job.work_mode or "",
            job.employment_type or "",
            job.match_score if job.match_score is not None else "",
            " ; ".join(job.match_strengths or []),
            " ; ".join(job.match_gaps or []),
            job.match_recommendation or "",
            job.status or "Ej ansökt",
            job.application_url or build_fallback_job_link(job),
            job.source_platform or "",
        ])

    return output.getvalue()

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

async def run_search_workflow(query: str, location: str, skills: str, min_score: int):
    q_enc = urllib.parse.quote(query)
    l_enc = urllib.parse.quote(location)

    sources = [
        {
            "url": f"https://arbetsformedlingen.se/platsbanken/annonser?q={q_enc}%20{l_enc}",
            "platform": "Platsbanken",
        },
        {
            "url": f"https://se.indeed.com/jobs?q={q_enc}&l={l_enc}",
            "platform": "Indeed",
        },
        {
            "url": f"https://www.linkedin.com/jobs/search?keywords={q_enc}&location={l_enc}",
            "platform": "LinkedIn",
        },
        {
            "url": f"https://jobbsafari.se/jobb?q={q_enc}&l={l_enc}",
            "platform": "JobbSafari",
        },
    ]

    async def process_source(source):
        md = await fetch_webpage(source["url"])
        extracted = await extract_jobs_with_ai(md, source["url"])
        for job in extracted:
            job.source_platform = source["platform"]
        return extracted

    results = await asyncio.gather(*(process_source(s) for s in sources))

    # Dubblettfilter
    all_jobs = []
    seen_jobs = set()

    for job_list in results:
        for job in job_list:
            title_key = (job.title or "").lower().strip()
            company_key = (job.company or "").lower().strip()
            key = f"{title_key}|{company_key}"

            if key not in seen_jobs:
                seen_jobs.add(key)
                all_jobs.append(job)

    # Poängsätt mot CV
    scored_jobs = await score_jobs_with_ai(all_jobs, skills)
    return [job for job in scored_jobs if (job.match_score or 0) >= min_score]


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
                all_found_jobs = asyncio.run(
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

            except Exception as e:
                st.error(f"Ett fel uppstod: {e}")


# --- VISNING AV SPARADE RESULTAT ---

st.subheader("📋 Resultat")
if st.session_state.search_ran:
    saved_results = st.session_state.search_results

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

            if job.short_motivation:
                st.write("**📝 Kort motivation:**")
                st.write(job.short_motivation)

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

            st.markdown(f"[{link_label}]({link})")
else:
    st.caption("Inga sparade jobb ännu.")
