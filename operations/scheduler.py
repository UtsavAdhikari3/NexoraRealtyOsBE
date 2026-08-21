from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import ScheduledJob


@dataclass
class ScheduledJobExecution:
    name: str
    claimed: bool
    result: dict = field(default_factory=dict)


def _claim(name, lease_seconds):
    now = timezone.now()
    with transaction.atomic():
        job, _ = ScheduledJob.objects.select_for_update().get_or_create(name=name)
        if job.locked_until and job.locked_until > now:
            return False
        job.locked_until = now + timedelta(seconds=lease_seconds)
        job.last_started_at = now
        job.run_count += 1
        job.save(update_fields=[
            "locked_until", "last_started_at", "run_count", "updated_at",
        ])
    return True


def _finish(name, *, result=None, error=None):
    now = timezone.now()
    with transaction.atomic():
        job = ScheduledJob.objects.select_for_update().get(name=name)
        job.locked_until = None
        if error is None:
            job.last_succeeded_at = now
            job.last_error = ""
            job.last_result = result or {}
            fields = [
                "locked_until", "last_succeeded_at", "last_error",
                "last_result", "updated_at",
            ]
        else:
            job.last_failed_at = now
            job.last_error = str(error)[:4000]
            job.failure_count += 1
            fields = [
                "locked_until", "last_failed_at", "last_error",
                "failure_count", "updated_at",
            ]
        job.save(update_fields=fields)


@contextmanager
def scheduled_job(name, *, lease_seconds=1800):
    """Claim a named job, record health, and skip concurrent invocations."""
    execution = ScheduledJobExecution(
        name=name,
        claimed=_claim(name, lease_seconds),
    )
    if not execution.claimed:
        yield execution
        return
    try:
        yield execution
    except Exception as exc:
        _finish(name, error=exc)
        raise
    else:
        _finish(name, result=execution.result)
