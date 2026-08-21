import logging

from django.core.management.base import BaseCommand

from operations.models import Task
from operations.scheduler import scheduled_job
from operations.task_recurrence import create_next_task_occurrence

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Create missing next occurrences for completed recurring tasks."

    def handle(self, *args, **options):
        with scheduled_job("recurring-tasks") as job:
            if not job.claimed:
                self.stdout.write("Skipped recurring tasks; another worker holds the lease.")
                return
            created = 0
            queryset = Task.objects.filter(
                status="done",
                recurrence__in=["daily", "weekly", "monthly"],
                due_at__isnull=False,
                next_occurrence__isnull=True,
            )
            failed = 0
            for task in queryset.iterator():
                try:
                    _, was_created = create_next_task_occurrence(task)
                    created += int(was_created)
                except Exception:
                    failed += 1
                    logger.exception("Recurring task generation failed for task %s", task.id)
            job.result = {"created": created, "failed": failed}
        self.stdout.write(self.style.SUCCESS(
            f"Created {created} recurring task occurrences; {failed} failed."
        ))
