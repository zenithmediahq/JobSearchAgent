# AI Job Search Agent

An AI‑powered job search application built with **Streamlit** to find, analyze, save, and track job postings based on a candidate’s CV.

The app helps users:

- search jobs across multiple job boards  
- extract job postings using AI  
- match jobs against an uploaded CV  
- save interesting jobs  
- track application status  
- generate application packs (motivation, cover letter, CV tailoring tips)  
- export results to CSV and application packs to TXT  

---

## Features

### Multi‑source job search
The app retrieves jobs from:

- Arbetsförmedlingen Platsbanken  
- Indeed  
- LinkedIn  
- JobbSafari  

### CV‑based matching
Users can:

- upload a CV as **PDF, DOCX, or TXT**  
- paste CV text manually  

The AI compares each job with the CV and provides:

- **match score**  
- **strengths**  
- **gaps**  
- **recommendation**  

### Smart filters
Filtering options include:

- minimum AI match score  
- remote/hybrid  
- full‑time  

### Saved jobs
Users can maintain a saved list with:

- save job  
- remove job  
- export saved jobs to CSV  

### Status tracking
Each saved job can be assigned a status:

- Not applied  
- Applied  
- Interview  
- Rejected  

### Application Pack
For saved jobs, the app can generate:

- short motivation  
- cover letter  
- CV tailoring suggestions  

### Export options
Supported export formats:

- search results → CSV  
- saved jobs → CSV  
- application packs → TXT  

### Search diagnostics
After each search, the app displays:

- fetch status per source  
- number of extracted jobs per source  
- jobs before duplicate filtering  
- jobs after duplicate filtering  
- jobs after AI score filtering  
- jobs after UI filters  

---

## How it works

### 1. CV input
The user uploads a CV or pastes profile text.

### 2. Job search
The app constructs search URLs for multiple job boards.

### 3. Fetch & extraction
Job pages are fetched via the Linkup API, which returns readable text/markdown.

### 4. AI extraction
Gemini extracts structured job postings from raw page content.

### 5. AI scoring
Each job is evaluated against the CV using recruiter‑style logic.

### 6. User workflow
Users can:

- review results  
- save jobs  
- set status  
- generate application packs  
- export data  

---

## Tech stack

- Python  
- Streamlit  
- OpenAI‑compatible Gemini API  
- Linkup API  
- httpx  
- Pydantic  
- PyMuPDF  
- python-docx  

---

## Project structure

```
.
├── app.py
├── models.py
├── services/
│   ├── __init__.py
│   ├── ai_client.py
│   ├── application_pack.py
│   ├── cv_parser.py
│   ├── job_fetcher.py
│   └── job_scoring.py
├── utils/
│   ├── __init__.py
│   ├── export.py
│   └── job_state.py
└── requirements.txt
```

---

## Example workflow

1. Upload your CV  
2. Enter job title and location  
3. Start the search  
4. Review match scores and recommendations  
5. Save interesting jobs  
6. Set job status  
7. Generate application packs  
8. Copy or download the generated content  
9. Apply  

---

## Current capabilities

The app currently supports:

- multiple job sources  
- AI‑based job extraction  
- AI‑based CV matching  
- per‑source diagnostics  
- saved jobs  
- status tracking  
- AI‑generated application packs  
- CSV/TXT export  

---

## Known limitations

- Job boards may change HTML structure or block traffic  
- AI extraction depends on how readable the source content is  
- Match score is heuristic, not absolute truth  
- Application Pack may require manual refinement  
- Session state is temporary and not a real database  
- No dedicated “copy to clipboard” button yet  

---

## Roadmap

Potential next steps:

- UI polish  
- enhanced diagnostics  
- more export formats  
- database‑backed storage  
- favorite filters and sorting  
- copy‑buttons  
- improved CV tailoring  
- better per‑source error handling  
- deployment improvements  

---

## Safety & design principles

The Application Pack is intentionally designed to **avoid**:

- inventing experience  
- inventing education  
- inventing certifications  
- overly fluffy or unrealistic writing  

The goal is to help users write stronger applications without generating false credentials.

---

## Why this project exists

Job searching is often repetitive, messy, and time‑consuming. This project was created to reduce manual work by combining:

- web data retrieval  
- AI‑based structuring  
- CV matching  
- application support  
- simple tracking  

---
