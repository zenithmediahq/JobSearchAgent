from sqlmodel import select

from db import get_session
from models import JobListing, SavedJobRecord


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
        status=job.status
        short_motivation=job.short_motivation,
        cover_letter=job.cover_letter,
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
