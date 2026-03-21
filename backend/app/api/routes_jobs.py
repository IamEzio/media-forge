"""HTTP routes for job submission, status checks, and downloads."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..models.job_models import JobStatusResponse, JobType
from ..services.job_service import job_service
from ..services.storage_service import storage_service


router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobStatusResponse)
async def submit_job(
	job_type: JobType = Form(..., description="Type of processing to perform"),
	video: UploadFile = File(..., description="Input video file"),
	subtitles: UploadFile | None = File(
		default=None, description="Optional .srt subtitles file for overlay jobs"
	),
):
    """Submit a new media processing job.

    Accepts multipart form-data containing the video file, an optional
    subtitles file, and the desired job_type. Returns the enqueued
    job_id and initial status.
    """

    if job_type == JobType.OVERLAY and subtitles is None:
        raise HTTPException(status_code=400, detail="subtitles file is required for overlay jobs")

    # Persist uploaded files to shared storage.
    video_path = storage_service.save_upload(video)
    subtitles_path_str: str | None = None

    if subtitles is not None:
        subtitles_path = storage_service.save_upload(subtitles)
        subtitles_path_str = str(subtitles_path)

    job_id = job_service.submit_job(job_type=job_type, video_path=str(video_path), subtitles_path=subtitles_path_str)

    return JobStatusResponse(job_id=job_id, status="pending")


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str) -> JobStatusResponse:
    """Return the current status of the given job."""

    return job_service.get_status(job_id)


@router.get("/{job_id}/download")
async def download_result(job_id: str, job_type: JobType) -> FileResponse:
    """Stream the processed output file to the client.

    The client should pass the job_type used when creating the job so
    we can compute the deterministic output path. In a more advanced
    system, job metadata would be persisted in a database instead.
    """

    output_path: Path = storage_service.get_output_path_for_job(job_id, job_type)

    if not output_path.is_file():
        raise HTTPException(status_code=404, detail="Output not available yet")

    return FileResponse(
        path=str(output_path),
        filename=output_path.name,
        media_type="application/octet-stream",
    )
