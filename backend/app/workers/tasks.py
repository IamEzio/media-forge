"""Celery tasks for media processing.

Tasks are designed to be idempotent and resilient. They use
exponential backoff with a bounded number of retries and short-circuit
when output files already exist.
"""

from __future__ import annotations

import logging
from pathlib import Path

from celery import Task

from ..core.celery_app import celery_app
from ..models.job_models import JobType
from ..services.storage_service import storage_service
from .ffmpeg_service import (
    FFmpegError,
    build_extract_command,
    build_overlay_command,
    build_transcode_command,
    run_ffmpeg,
)


logger = logging.getLogger(__name__)


class BaseMediaTask(Task):
    autoretry_for = (FFmpegError,)
    retry_kwargs = {"max_retries": 5}
    retry_backoff = True  # exponential backoff
    retry_backoff_max = 600  # up to 10 minutes between retries
    retry_jitter = True


@celery_app.task(bind=True, base=BaseMediaTask, name="process_media_task")
def process_media_task(
    self,
    job_type: str,
    input_path: str,
    subtitles_path: str | None = None,
) -> dict:
    """Celery task that performs the requested media processing.

    Parameters are simple strings so they can be serialized easily
    across the Celery transport. The function resolves input/output
    paths and invokes FFmpeg via the helper service.
    """

    job_type_enum = JobType(job_type)
    input_p = Path(input_path)

    if not input_p.is_file():
        # Non-retriable error: input is missing.
        msg = f"Input file not found: {input_p}"
        logger.error(msg)
        raise FileNotFoundError(msg)

    output_path = storage_service.get_output_path_for_job(self.request.id, job_type_enum)

    # Idempotency: if the file is already there and non-empty, succeed.
    if storage_service.output_exists_and_nonempty(output_path):
        logger.info("Output already exists for job %s, skipping", self.request.id)
        return {"output_path": str(output_path)}

    if job_type_enum == JobType.OVERLAY:
        if not subtitles_path:
            raise ValueError("subtitles_path is required for overlay jobs")
        sub_p = Path(subtitles_path)
        if not sub_p.is_file():
            raise FileNotFoundError(f"Subtitles file not found: {sub_p}")
        cmd = build_overlay_command(input_p, sub_p, output_path)
    elif job_type_enum == JobType.TRANSCODE:
        cmd = build_transcode_command(input_p, output_path)
    elif job_type_enum == JobType.EXTRACT:
        cmd = build_extract_command(input_p, output_path)
    else:
        raise ValueError(f"Unsupported job type: {job_type}")

    logger.info(
        "Starting FFmpeg job",
        extra={
            "job_id": self.request.id,
            "job_type": job_type_enum.value,
            "input": str(input_p),
            "output": str(output_path),
        },
    )

    # Any FFmpegError raised here will trigger Celery's autoretry.
    run_ffmpeg(cmd)

    logger.info("Completed FFmpeg job %s", self.request.id)
    return {"output_path": str(output_path)}
