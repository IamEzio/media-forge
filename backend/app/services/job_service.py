"""Job service orchestrating task submission and status lookup."""

from __future__ import annotations

from celery.result import AsyncResult

from ..core.celery_app import celery_app
from ..models.job_models import JobStatusResponse, JobType, map_celery_state
from ..services.storage_service import storage_service


class JobService:
    """High-level façade for job creation and tracking.

    This keeps FastAPI route handlers thin and makes it easier to adapt
    the implementation (e.g. swap Celery, add a DB) without changing
    the HTTP layer.
    """

    def submit_job(
        self,
        job_type: JobType,
        video_path: str,
        subtitles_path: str | None = None,
    ) -> str:
        """Enqueue a media processing task and return its job_id.

        We use the Celery task id directly as the external job_id. This
        avoids an additional persistence layer while still providing a
        unique, traceable identifier.
        """

        from ..workers.tasks import process_media_task

        # The task itself will compute the deterministic output path.
        async_result = process_media_task.delay(
            job_type=job_type.value,
            input_path=video_path,
            subtitles_path=subtitles_path,
        )
        return async_result.id

    def get_status(self, job_id: str) -> JobStatusResponse:
        result = AsyncResult(job_id, app=celery_app)
        status = map_celery_state(result.state, result.failed())

        output_url = None
        error_msg = None

        if status == status.COMPLETED:
            # URL where the API exposes the processed file.
            output_url = f"/jobs/{job_id}/download"
        elif status == status.FAILED:
            # Surface a truncated error message, if any, for debugging.
            try:
                info = result.info
                if isinstance(info, Exception):
                    error_msg = str(info)
                elif isinstance(info, dict) and "error" in info:
                    error_msg = str(info["error"])
            except Exception:
                error_msg = None

        return JobStatusResponse(
            job_id=job_id,
            status=status,
            output_url=output_url,
            error=error_msg,
        )


job_service = JobService()
