"""Storage service encapsulating filesystem operations.

The API and workers share a Docker volume mounted at /data. This
service centralizes how input and output paths are constructed and how
files are persisted, improving testability and separation of concerns.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import BinaryIO

from fastapi import UploadFile

from ..core.config import settings
from ..models.job_models import JobType


class StorageService:
    """Service responsible for managing media files on disk."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or settings.data_dir
        self.input_dir = settings.input_dir
        self.output_dir = settings.output_dir
        self.temp_dir = settings.temp_dir

        # Ensure directories exist on startup of each process.
        for d in (self.input_dir, self.output_dir, self.temp_dir):
            d.mkdir(parents=True, exist_ok=True)

    def save_upload(self, file: UploadFile, dest_dir: Path | None = None) -> Path:
        """Persist an uploaded file to the filesystem.

        Uses the provided filename from the client while guarding
        against directory traversal. In a more hardened system, we could
        further sanitize and/or randomize filenames per upload.
        """

        target_dir = dest_dir or self.input_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        safe_name = os.path.basename(file.filename or "upload.bin")
        dest_path = target_dir / safe_name

        with dest_path.open("wb") as out_f:
            # Iterating over chunks keeps memory usage bounded for large uploads.
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                out_f.write(chunk)

        return dest_path

    def get_output_path_for_job(self, job_id: str, job_type: JobType) -> Path:
        """Compute deterministic output path for a given job.

        Deterministic naming makes tasks idempotent: retries will write
        to the same location, and workers can short-circuit if a
        non-empty file already exists.
        """

        if job_type == JobType.EXTRACT:
            ext = ".mp3"
        else:
            ext = ".mp4"

        filename = f"{job_id}_{job_type.value}{ext}"
        return self.output_dir / filename

    def output_exists_and_nonempty(self, path: Path) -> bool:
        return path.is_file() and path.stat().st_size > 0

    def open_binary(self, path: Path) -> BinaryIO:
        return path.open("rb")


storage_service = StorageService()
