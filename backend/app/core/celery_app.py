"""Celery application instance shared by API and workers.

The API imports this module to enqueue tasks, and the worker container
uses it as the Celery application entrypoint. Centralizing Celery
configuration here avoids duplication and keeps broker/result
configuration consistent across processes.
"""

from __future__ import annotations

from celery import Celery

from .config import settings


def _make_celery() -> Celery:
    """Create and configure the Celery app.

    We configure Redis as both broker and result backend and set JSON as
    the default serializer to keep messages language-agnostic.
    """

    app = Celery(
        "media_forge",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
        include=["backend.app.workers.tasks"],
    )

    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_acks_late=True,  # prefer at-least-once semantics
        worker_prefetch_multiplier=1,  # fair scheduling
    )

    return app


celery_app = _make_celery()
