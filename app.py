import streamlit as st
import asyncio
import logging
import urllib.parse
import httpx
from pydantic import BaseModel, Field
from openai import AsyncOpenAI

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
# AI och Sök-funktioner
# -------------------------
def get_api_key(secret_name):
    """Hämtar nycklar från Streamlits inbyggda valv."""
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
                {"role": "system", "content": "Extrahera alla jobbannonser. Identifiera titel, företag, plats, länk och beskrivning."},
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
                    "content": "Du är en stenhård rekryterare. Betygsätt varje jobb 0-100 baserat på kandidatens CV. Var kritisk. 0-39 poäng om nyckelkrav saknas. Ge kort, ärlig motivering på svenska."
                },
                {"role": "user", "content": f"Kandidat:\n{skills}\n\nJobbannonser:\n{chr(10).join(job_summaries)}"}
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

    # Kör alla webbsidor samtidigt!
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
st.markdown("Fyll i dina sökkriterier och klistra in ditt CV nedan. AI:n skannar de största plattformarna och matchar annonserna mot din erfarenhet.")

with st.sidebar:
    st.header("🔍 Sökinställningar")
    query = st.text_input("Jobbtitel / Sökord", value="IT support")
    location = st.text_input("Plats", value="Skåne")
    min_score = st.slider("Lägsta AI-matchning (%)", 0, 100, 40, 5)
    st.info("Skannar: Platsbanken, LinkedIn, Indeed & JobbSafari")

st.subheader("📄 Din profil / Ditt CV")
cv_text = st.text_area("Klistra in ditt CV eller en beskrivning av din erfarenhet här:", height=200)

if st.button("🚀 Starta AI-sökning", type="primary", use_container_width=True):
    if not cv_text.strip():
        st.warning("⚠️ Du måste klistra in ditt CV först!")
    else:
        with st.spinner("🤖 Agenten söker av nätet och läser annonser... (Tar ca 30-60 sek)"):
            try:
                # Startar det asynkrona AI-flödet i bakgrunden
                jobs = asyncio.run(run_search_workflow(query, location, cv_text, min_score))
                
                if not jobs:
                    st.info("🤷‍♂️ Hittade inga jobb som matchade dina strikta krav. Prova att sänka procent-spärren.")
                else:
                    st.success(f"✅ Sökning klar! Hittade {len(jobs)} unika jobb över {min_score}% matchning.")
                    
                    for job in jobs:
                        score = job.match_score or 0
                        color = "🟢" if score >= 80 else "🟡" if score >= 60 else "🔴"
                        
                        link = job.application_url
                        if not link or str(link).lower() == "none":
                            c_enc, t_enc = urllib.parse.quote(job.company), urllib.parse.quote(job.title)
                            link = f"https://www.google.com/search?q={c_enc}+{t_enc}+jobb"
                            link_label = "🔍 Googla jobbet (Länk saknas)"
                        else:
                            link_label = "🔗 Gå till ansökan"

                        with st.expander(f"{color} [{score}%] {job.title} @ {job.company}"):
                            c1, c2 = st.columns(2)
                            c1.write(f"**📍 Plats:** {job.location}")
                            c2.write(f"**🌐 Källa:** {job.source_platform}")
                            st.info(f"**💡 AI-Motivering:** {job.match_reason}")
                            st.markdown(f"[{link_label}]({link})")
            except Exception as e:
                st.error(f"Ett fel uppstod: {e}")