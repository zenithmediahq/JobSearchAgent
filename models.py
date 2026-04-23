from pydantic import BaseModel
from sqlmodel import Field, SQLModel


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


class ResumeSectionScore(BaseModel):
    section: str
    score: int
    findings: list[str]


class KeywordGap(BaseModel):
    keyword: str
    importance: str
    present_in_cv: bool
    evidence: str | None = None


class BulletRewriteSuggestion(BaseModel):
    original: str
    suggestion: str
    reason: str


class ResumeScanResult(BaseModel):
    overall_score: int
    summary: str
    strengths: list[str]
    weaknesses: list[str]
    missing_sections: list[str]
    ats_risks: list[str]
    section_scores: list[ResumeSectionScore]
    keyword_gaps: list[KeywordGap]
    bullet_suggestions: list[BulletRewriteSuggestion]
    recommended_keywords: list[str]


class TailoredResumeBullet(BaseModel):
    original: str | None = None
    tailored: str
    reason: str


class TailoredResumeSection(BaseModel):
    heading: str
    strategy: str
    content: list[str]
    bullets: list[TailoredResumeBullet]


class TailoredResumeResult(BaseModel):
    target_role: str
    target_company: str
    positioning_summary: str
    rewritten_profile: str
    sections: list[TailoredResumeSection]
    keywords_used: list[str]
    keywords_to_add: list[str]
    missing_but_not_invented: list[str]
    recruiter_notes: list[str]


class InterviewQuestion(BaseModel):
    id: str
    category: str
    question: str
    what_good_answers_include: list[str]


class InterviewQuestionSet(BaseModel):
    target_role: str
    target_company: str
    questions: list[InterviewQuestion]


class InterviewAnswerFeedback(BaseModel):
    question_id: str
    score: int
    strengths: list[str]
    weaknesses: list[str]
    improved_answer: str


class InterviewFeedbackSet(BaseModel):
    overall_score: int
    overall_summary: str
    feedback: list[InterviewAnswerFeedback]


class SavedJobRecord(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    job_key: str = Field(index=True, unique=True)

    title: str
    company: str
    location: str
    description: str

    work_mode: str | None = None
    employment_type: str | None = None
    application_url: str | None = None
    source_platform: str | None = None

    match_score: int | None = None
    status: str = "Ej ansökt"

    short_motivation: str | None = None
    cover_letter: str | None = None
