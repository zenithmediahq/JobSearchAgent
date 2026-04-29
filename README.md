# JobSearchAgent

JobSearchAgent is a Streamlit-based job search assistant for finding, evaluating, saving, and preparing job applications from a candidate CV.

The project is inspired by commercial AI job-search tools, but the goal is to build an open, practical workflow that helps users:

- search for jobs by role and location
- compare jobs against an uploaded CV
- scan a CV for ATS risks
- tailor CV content for selected jobs
- generate application material
- practice interview questions
- save jobs and track application status

The app is still evolving, but the current direction is to keep Streamlit as the UI while moving product logic into focused service modules.

---

## Current Features

### Job Search

Users can search by job title/keyword and location. The current reliable source path is:

- Platsbanken through the official JobTech JobSearch API

The app also contains experimental fallback support for:

- Indeed
- LinkedIn
- JobbSafari

Those sources are less reliable because they often block scraping or return search/category pages instead of individual job ads.

### CV Upload

Users can provide their CV by:

- uploading PDF, DOCX, or TXT files
- pasting CV text manually

The parsed CV text is used for job matching, resume scanning, tailoring, and interview preparation.

### Job Matching

Jobs are normalized into a shared `JobListing` model and scored against the CV.

The app supports:

- AI-based scoring with Gemini
- fallback keyword scoring when AI scoring fails or quota is unavailable
- match strengths
- match gaps
- short recommendations
- minimum score filtering
- remote/hybrid filtering
- full-time filtering

### ATS Resume Scanner

The CV Scanner tab analyzes a CV for ATS-style issues and returns:

- overall ATS score
- summary
- strengths
- weaknesses
- missing sections
- ATS risks
- section scores
- keyword gaps
- bullet rewrite suggestions
- recommended keywords

The scanner can run as a general CV review and also supports job-targeted scanning.

### Tailored Resume Builder

The CV Builder tab helps adapt existing CV content toward a selected job without inventing credentials.

It focuses on:

- role targeting
- safer rewrites
- keyword alignment
- concrete improvement suggestions

### Interview Practice

The Intervju tab supports mock interview preparation based on the CV and selected job context.

The project includes interview models and service logic for structured interview sessions.

### Saved Jobs and Application Workflow

Users can:

- save jobs
- remove saved jobs
- update status
- generate application packs
- export search results and saved jobs as CSV
- download application pack text

Saved job and interview persistence has started moving toward SQLite-backed storage.

### Search Diagnostics

Each search includes diagnostics so source reliability is visible:

- source fetch status
- source URL or API endpoint
- number of jobs extracted
- number of fallback search results
- number of rejected fallback results
- jobs before and after deduplication
- jobs after score filtering
- returned result count

---

## Tech Stack

- Python
- Streamlit
- Pydantic
- SQLModel / SQLite
- httpx
- OpenAI-compatible Gemini API
- Linkup API for experimental fallback fetching/search
- JobTech JobSearch API for Platsbanken
- PyMuPDF
- python-docx

---

## Project Structure

```text
.
|-- app.py
|-- db.py
|-- models.py
|-- requirements.txt
|-- services/
|   |-- ai_client.py
|   |-- application_pack.py
|   |-- cv_parser.py
|   |-- interview_practice.py
|   |-- job_fetcher.py
|   |-- job_scoring.py
|   |-- resume_scanner.py
|   |-- resume_tailor.py
|   |-- storage.py
|   `-- job_sources/
|       |-- __init__.py
|       `-- platsbanken.py
|-- ui/
|   |-- interview_tab.py
|   |-- profile_input.py
|   |-- results_tab.py
|   |-- saved_jobs_tab.py
|   |-- scanner_tab.py
|   |-- sidebar.py
|   `-- tailored_resume_tab.py
|-- utils/
|   |-- export.py
|   `-- job_state.py
`-- .streamlit/
    `-- secrets.example.toml
```

---

## Configuration

The app needs API keys for AI features and fallback source fetching.

Create Streamlit secrets with:

```toml
GEMINI_API_KEY = "your-gemini-api-key"
LINKUP_API_KEY = "your-linkup-api-key"
```

For Streamlit Cloud, add these values in the app's Secrets settings.

Do not commit real secrets. The repo should only contain `.streamlit/secrets.example.toml`.

---

## Running Locally

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the app:

```bash
streamlit run app.py
```

---

## Example Workflow

1. Upload or paste a CV.
2. Enter a job title and location.
3. Choose job sources.
4. Start the search.
5. Review ranked matches and diagnostics.
6. Save interesting jobs.
7. Scan or tailor the CV.
8. Generate application material.
9. Practice interview questions.
10. Track saved job status.

---

## Current Development Focus

The current priority is reliability before adding more automation.

Recent direction:

- use structured APIs where possible
- make Platsbanken reliable through JobTech API
- keep Indeed/LinkedIn as experimental fallback sources
- reduce dependence on AI extraction for job fetching
- keep AI for scoring, resume analysis, tailoring, and interview preparation
- continue moving durable product data out of `st.session_state`

Recommended next improvements:

- pass the user search query into fallback scoring
- improve Platsbanken ranking and source diagnostics labels
- make AI scoring cheaper and more robust
- add better source adapters for each job provider
- improve SQLite persistence and saved search history
- polish the scanner and CV builder UX

---

## Known Limitations

- Indeed and LinkedIn are unreliable through scraping/fallback search.
- Fallback scoring is keyword-based and less accurate than AI scoring.
- AI features depend on Gemini API availability and quota.
- Some source results may be broad or weak matches before scoring.
- SQLite persistence is still early and not a full production data layer.
- Streamlit Cloud file persistence may not behave like a production database.

---

## Safety Principles

The app should not invent user credentials.

Generated CV and application content should avoid:

- invented work experience
- invented education
- invented certifications
- invented achievements
- unrealistic claims

The goal is to help users present real experience more clearly, not fabricate qualifications.

---

## Why This Exists

Job searching is repetitive and fragmented. JobSearchAgent is being built to combine job discovery, CV matching, ATS feedback, tailoring, interview preparation, and application tracking in one practical assistant.
