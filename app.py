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
    match_reason: str | None = None

class JobListings(BaseModel):
    jobs: list[JobListing]
    total_count: int

class ScoredJob(BaseModel):
    index: int
    score: int
    reason: str

class ScoringResult(BaseModel):
    scored_jobs: list[ScoredJob]

# -------------------------
# Hjälpfunktion för att läsa CV-filer
# -------------------------
def extract_text_from_upload(uploaded_file) -> str:
    """Extraherar text från PDF, Word eller TXT-filer."""
    file_bytes = uploaded_file.read()
    filename = uploaded_file.name.lower()
    
    if filename.endswith(".pdf"):
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        return "\n".join([page.get_text() for page in doc]).strip()
    elif filename.endswith((".docx", ".doc")):
        doc = Document(BytesIO(file_bytes))
        return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
    else:
        return file_bytes.decode("utf-8", errors="replace")

# -------------------------
# AI och Sök-funktioner
# -------------------------
def get_api_key(secret_name):
    try:
        return st.secrets[secret_name]
    except Exception:
        st.error(f"Saknar API-nyckel: {secret_name}")
        st.stop()

def get_ai_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=get_api_key("GEMINI_API_KEY"),
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
    )

async def fetch_webpage(url: str) -> str:
    headers = {"Authorization": f"Bearer {get_api_key('LINKUP_API_KEY')}", "Content-Type": "application/json"}
    payload = {"url": url, "includeRawHtml": False, "renderJs": True, "extractImages": False}
    
    async with httpx.AsyncClient(timeout=120) as client:
        try:
            response = await client.post(LINKUP_API_URL, headers=headers, json=payload)
            response.raise_for_status()
            return response.json().get("markdown", "")
        except Exception as e:
            logger.warning(f"Kunde inte läsa {url}: {e}")
            return ""

async def extract_jobs_with_ai(markdown: str, url: str) -> list[JobListing]:
    if not markdown: return []
    markdown = markdown[:MAX_CONTENT_CHARS]
    
    client = get_ai_client()
    try:
        response = await client.beta.chat.completions.parse(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": "Extrahera alla jobbannonser. Identifiera titel, företag, plats, länk, arbetsform (distans/hybrid/på plats), anställningstyp (heltid/deltid) och beskrivning."},
                {"role": "user", "content": f"URL: {url}\n\nInnehåll:\n{markdown}"}
            ],
            response_format=JobListings
        )
        return response.choices[0].message.parsed.jobs
    except Exception as e:
        logger.error(f"AI Extraktionsfel: {e}")
        return []

async def score_jobs_with_ai(jobs: list[JobListing], skills: str) -> list[JobListing]:
    if not jobs: return []
    job_summaries = [f"[{i}] {j.title} @ {j.company} | {j.description[:2000]}" for i, j in enumerate(jobs)]
    
    client = get_ai_client()
    try:
        response = await client.beta.chat.completions.parse(
            model=AI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Du är en stenhård rekryterare. Betygsätt varje jobb 0-100 baserat på hur väl kandidatens CV matchar kraven. Ge kort motivering på svenska."
                },
                {"role": "user", "content": f"Kandidatens CV:\n{skills}\n\nJobbannonser:\n{chr(10).join(job_summaries)}"}
            ],
            response_format=ScoringResult,
        )
        
        score_map = {s.index: s for s in response.choices[0].message.parsed.scored_jobs}
        for i, job in enumerate(jobs):
            if i in score_map:
                job.match_score = score_map[i].score
                job.match_reason = score_map[i].reason
                
        jobs.sort(key=lambda j: j.match_score if j.match_score is not None else 0, reverse=True)
    except Exception as e:
        logger.error(f"Scoring fel: {e}")
    
    return jobs

def jobs_to_csv(jobs: list[JobListing]) -> str:
    """Konverterar jobblistan till CSV-format."""
    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Title",
        "Company",
        "Location",
        "Work Mode",
        "Employment Type",
        "Match Score",
        "Match Reason",
        "Application Link",
        "Source"
    ])

    for job in jobs:
        writer.writerow([
            job.title or "",
            job.company or "",
            job.location or "",
            job.work_mode or "",
            job.employment_type or "",
            job.match_score if job.match_score is not None else "",
            job.match_reason or "",
            job.application_url or f"https://www.google.com/search?q={urllib.parse.quote(job.company)}+{urllib.parse.quote(job.title)}+jobb",
            job.source_platform or ""
        ])

    return output.getvalue()

async def run_search_workflow(query: str, location: str, skills: str, min_score: int):
    q_enc = urllib.parse.quote(query)
    l_enc = urllib.parse.quote(location)
    
    sources = [
        {"url": f"https://arbetsformedlingen.se/platsbanken/annonser?q={q_enc}%20{l_enc}", "platform": "Platsbanken"},
        {"url": f"https://se.indeed.com/jobs?q={q_enc}&l={l_enc}", "platform": "Indeed"},
        {"url": f"https://www.linkedin.com/jobs/search?keywords={q_enc}&location={l_enc}", "platform": "LinkedIn"},
        {"url": f"https://jobbsafari.se/jobb?q={q_enc}&l={l_enc}", "platform": "JobbSafari"}
    ]
    
    async def process_source(source):
        md = await fetch_webpage(source["url"])
        extracted = await extract_jobs_with_ai(md, source["url"])
        for j in extracted: j.source_platform = source["platform"]
        return extracted

    results = await asyncio.gather(*(process_source(s) for s in sources))
    
    # Dubblettfilter
    all_jobs = []
    seen_jobs = set()
    for job_list in results:
        for job in job_list:
            key = f"{job.title.lower().strip()}|{job.company.lower().strip()}"
            if key not in seen_jobs:
                seen_jobs.add(key)
                all_jobs.append(job)
                
    # Poängsätt mot CV
    scored_jobs = await score_jobs_with_ai(all_jobs, skills)
    return [j for j in scored_jobs if (j.match_score or 0) >= min_score]

# -------------------------
# WEBBGRÄNSSNITT (UI)
# -------------------------
st.title("💼 Din Personliga AI-Rekryterare")
st.markdown("Ladda upp ditt CV och fyll i vad du letar efter. AI:n skannar marknaden, filtrerar bort bruset och presenterar endast jobben som passar dig.")

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
uploaded_file = st.file_uploader("Dra och släpp ditt CV här (PDF eller Word)", type=["pdf", "docx", "doc", "txt"])
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
                # Hämta alla jobb som klarar min_score
                all_found_jobs = asyncio.run(run_search_workflow(query, location, final_cv_text, min_score))
                
                # --- APPLICERA EXTRA FILTER (Distans & Heltid) ---
                filtered_jobs = []
                for job in all_found_jobs:
                    # Kontrollera distans/hybrid
                    if filter_remote:
                        wm = str(job.work_mode).lower()
                        if "distans" not in wm and "hybrid" not in wm and "remote" not in wm:
                            continue # Hoppa över detta jobb
                    
                    # Kontrollera heltid
                    if filter_fulltime:
                        et = str(job.employment_type).lower()
                        if "heltid" not in et and "full-time" not in et and "full time" not in et:
                            continue # Hoppa över detta jobb
                            
                    filtered_jobs.append(job)
                
                # --- PRESENTATION ---
                if not filtered_jobs:
                    st.info("🤷‍♂️ Hittade inga jobb som klarade både matchningskravet och dina valda filter. Prova att ändra filtren!")
                else:
                    st.success(f"✅ Sökning klar! Hittade {len(filtered_jobs)} unika jobb som passar dina krav.")

                    csv_data = jobs_to_csv(filtered_jobs)
                    st.download_button(
                        label="📥 Ladda ner resultat som CSV",
                        data=csv_data,
                        file_name="job_results.csv",
                        mime="text/csv",
                        use_container_width=True
                    )

                    for job in filtered_jobs:
                        score = job.match_score or 0
                        color = "🟢" if score >= 80 else "🟡" if score >= 60 else "🔴"
                        
                        # Fixa saknade länkar
                        link = job.application_url
                        if not link or str(link).lower() == "none":
                            c_enc, t_enc = urllib.parse.quote(job.company), urllib.parse.quote(job.title)
                            link = f"https://www.google.com/search?q={c_enc}+{t_enc}+jobb"
                            link_label = "🔍 Googla jobbet (Länk saknas)"
                        else:
                            link_label = "🔗 Gå till ansökan"
                            
                        # Extra badges för arbetsform och anställningstyp
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
                            
                            if badge_str:
                                st.write(f"**Upplägg:** {badge_str}")
                                
                            st.info(f"**💡 AI-Motivering:** {job.match_reason}")
                            st.markdown(f"[{link_label}]({link})")
            except Exception as e:
                st.error(f"Ett fel uppstod: {e}")
