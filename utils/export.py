from io import StringIO
import csv
import urllib.parse
from models import JobListing


def build_fallback_job_link(job: JobListing) -> str:
    company = urllib.parse.quote(job.company or "")
    title = urllib.parse.quote(job.title or "")
    return f"https://www.google.com/search?q={company}+{title}+jobb"


def jobs_to_csv(jobs: list[JobListing]) -> str:
    output = StringIO()
    output.write("\ufeff")

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


def build_application_pack_text(job: JobListing) -> str:
    parts = [
        f"Titel: {job.title}",
        f"Företag: {job.company}",
        f"Plats: {job.location}",
        f"Status: {job.status}",
        "",
    ]

    if job.short_motivation:
        parts.append("KORT MOTIVATION")
        parts.append(job.short_motivation)
        parts.append("")

    if job.cover_letter:
        parts.append("PERSONLIGT BREV")
        parts.append(job.cover_letter)
        parts.append("")

    if job.cv_tailoring_tips:
        parts.append("CV-ANPASSNING")
        for tip in job.cv_tailoring_tips:
            parts.append(f"- {tip}")
        parts.append("")

    return "\n".join(parts).strip()
