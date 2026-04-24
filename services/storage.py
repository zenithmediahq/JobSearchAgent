from sqlmodel import select
import hashlib
from db import get_session
from models import (
    InterviewFeedbackSet,
    InterviewQuestionSet,
    InterviewSessionRecord,
    JobListing,
    SavedJobRecord,
)


def job_to_record(job: JobListing) -> SavedJobRecord:
    return SavedJobRecord(
        job_key=f"{(job.title or '').lower().strip()}|{(job.company or '').lower().strip()}",
        title=job.title,
        company=job.company,
        location=job.location,
        description=job.description,
        work_mode=job.work_mode,
        employment_type=job.employment_type,
        application_url=job.application_url,
        source_platform=job.source_platform,
        match_score=job.match_score,
        status=job.status,
        short_motivation=job.short_motivation,
        cover_letter=job.cover_letter,
        cv_tailoring_tips=job.cv_tailoring_tips,
    )


def record_to_job(record: SavedJobRecord) -> JobListing:
    return JobListing(
        title=record.title,
        company=record.company,
        location=record.location,
        description=record.description,
        work_mode=record.work_mode,
        employment_type=record.employment_type,
        application_url=record.application_url,
        source_platform=record.source_platform,
        match_score=record.match_score,
        status=record.status,
        short_motivation=record.short_motivation,
        cover_letter=record.cover_letter,
        cv_tailoring_tips=record.cv_tailoring_tips,
    )


def list_saved_job_records() -> list[SavedJobRecord]:
    with get_session() as session:
        statement = select(SavedJobRecord)
        return list(session.exec(statement))


def load_saved_jobs() -> list[JobListing]:
    return [record_to_job(record) for record in list_saved_job_records()]


def upsert_saved_job(job: JobListing) -> None:
    record = job_to_record(job)

    with get_session() as session:
        existing = session.exec(
            select(SavedJobRecord).where(
                SavedJobRecord.job_key == record.job_key)
        ).first()

        if existing:
            existing.title = record.title
            existing.company = record.company
            existing.location = record.location
            existing.description = record.description
            existing.work_mode = record.work_mode
            existing.employment_type = record.employment_type
            existing.application_url = record.application_url
            existing.source_platform = record.source_platform
            existing.match_score = record.match_score
            existing.status = record.status
            existing.short_motivation = record.short_motivation
            existing.cover_letter = record.cover_letter
            existing.cv_tailoring_tips = record.cv_tailoring_tips
            session.add(existing)
        else:
            session.add(record)

        session.commit()


def delete_saved_job(job_key: str) -> None:
    with get_session() as session:
        existing = session.exec(
            select(SavedJobRecord).where(SavedJobRecord.job_key == job_key)
        ).first()

        if existing:
            session.delete(existing)
            session.commit()


def build_interview_session_key(cv_text: str, job_key: str) -> str:
    cv_digest = hashlib.sha256(cv_text[:4000].encode("utf-8")).hexdigest()
    return f"{job_key}|{cv_digest}"


def load_interview_session(
    session_key: str,
) -> tuple[InterviewQuestionSet | None, InterviewFeedbackSet | None]:
    with get_session() as session:
        record = session.exec(
            select(InterviewSessionRecord).where(
                InterviewSessionRecord.session_key == session_key
            )
        ).first()

        if not record:
            return None, None

        question_set = InterviewQuestionSet.model_validate(
            record.questions_json)
        feedback_set = (
            InterviewFeedbackSet.model_validate(record.feedback_json)
            if record.feedback_json
            else None
        )

        return question_set, feedback_set


def upsert_interview_session(
    session_key: str,
    job_key: str,
    question_set: InterviewQuestionSet,
    feedback_set: InterviewFeedbackSet | None = None,
) -> None:
    with get_session() as session:
        existing = session.exec(
            select(InterviewSessionRecord).where(
                InterviewSessionRecord.session_key == session_key
            )
        ).first()

        question_payload = question_set.model_dump()
        feedback_payload = feedback_set.model_dump() if feedback_set else None

        if existing:
            existing.job_key = job_key
            existing.target_role = question_set.target_role
            existing.target_company = question_set.target_company
            existing.questions_json = question_payload
            existing.feedback_json = feedback_payload
            session.add(existing)
        else:
            session.add(
                InterviewSessionRecord(
                    session_key=session_key,
                    job_key=job_key,
                    target_role=question_set.target_role,
                    target_company=question_set.target_company,
                    questions_json=question_payload,
                    feedback_json=feedback_payload,
                )
            )

        session.commit()
