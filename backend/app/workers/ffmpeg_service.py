"""FFmpeg command construction and execution utilities.

All subprocess invocation is centralized here to keep Celery tasks
focused on orchestration rather than shell details.
"""

from __future__ import annotations

import logging
import shlex
import subprocess
from pathlib import Path
from typing import List


logger = logging.getLogger(__name__)


class FFmpegError(RuntimeError):
    """Raised when FFmpeg returns a non-zero exit code."""


def build_overlay_command(input_path: Path, subtitles_path: Path, output_path: Path) -> List[str]:
    return [
        "ffmpeg",
        "-y",  # overwrite output if it exists (important for idempotent retries)
        "-i",
        str(input_path),
        "-vf",
        f"subtitles={shlex.quote(str(subtitles_path))}",
        str(output_path),
    ]


def build_transcode_command(input_path: Path, output_path: Path) -> List[str]:
    return [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-vf",
        "scale=854:480",
        str(output_path),
    ]


def build_extract_command(input_path: Path, output_path: Path) -> List[str]:
    return [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-q:a",
        "0",
        "-map",
        "a",
        str(output_path),
    ]


def run_ffmpeg(cmd: List[str]) -> None:
    """Run an FFmpeg command and raise FFmpegError on failure.

    Stdout/stderr are captured and logged for observability and
    debugging. The calling Celery task can decide whether to retry
    based on this exception.
    """

    logger.info("Executing ffmpeg command", extra={"cmd": cmd})

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    logger.debug("ffmpeg stdout: %s", proc.stdout)
    if proc.stderr:
        logger.warning("ffmpeg stderr: %s", proc.stderr)

    if proc.returncode != 0:
        raise FFmpegError(f"ffmpeg failed with code {proc.returncode}")
