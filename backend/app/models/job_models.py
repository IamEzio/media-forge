"""Domain models for media processing jobs.

These Pydantic models are used both for request validation and
structuring responses from the API.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class JobType(str, Enum):
    OVERLAY = "overlay"
    TRANSCODE = "transcode"
    EXTRACT = "extract"


class JobCreateRequest(BaseModel):
    """Metadata for a job creation request.

    File contents are carried separately via multipart form upload; this
    model captures only the logical job configuration.
    """

    job_type: JobType = Field(..., description="Type of processing to perform")


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    output_url: Optional[str] = None
    error: Optional[str] = None


def map_celery_state(state: str, failed: bool) -> JobStatus:
    """Map a low-level Celery state to a simplified domain JobStatus.

    Celery has a rich state machine; for the API we collapse it into the
    four states defined in the requirements.
    """

    normalized = (state or "PENDING").upper()
    if normalized in {"PENDING", "RECEIVED"}:
        return JobStatus.PENDING
    if normalized in {"STARTED", "RETRY"}:
        return JobStatus.PROCESSING
    if normalized == "SUCCESS":
        return JobStatus.COMPLETED
    if normalized in {"FAILURE", "REVOKED"} or failed:
        return JobStatus.FAILED
    # Fallback to pending for any unknown state
    return JobStatus.PENDING
