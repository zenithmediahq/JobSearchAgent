from pydantic import BaseModel


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
