import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from operations.models import Lease, Notification, Task
from operations.scheduler import scheduled_job

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Create in-app reminders for tasks due in the next 24 hours."

    def handle(self, *args, **options):
        with scheduled_job("task-and-lease-reminders") as job:
            if not job.claimed:
                self.stdout.write("Skipped task reminders; another worker holds the lease.")
                return
            now = timezone.now()
            tasks = Task.objects.filter(
                status__in=["todo", "in_progress"],
                assigned_to__isnull=False,
                due_at__range=(now, now + timedelta(hours=24)),
                agency__is_active=True,
                agency__payment_status="paid",
            ).filter(
                Q(agency__subscription_expires_at__isnull=True)
                | Q(agency__subscription_expires_at__gt=now)
            )
            created = 0
            failed = 0
            for task in tasks.iterator():
                try:
                    _, was_created = Notification.objects.get_or_create(
                        user=task.assigned_to,
                        category="task_due",
                        link=f"/tasks?task={task.id}",
                        created_at__date=now.date(),
                        defaults={
                            "agency": task.agency,
                            "title": "Task due soon",
                            "message": task.title,
                        },
                    )
                    created += int(was_created)
                except Exception:
                    failed += 1
                    logger.exception("Task reminder failed for task %s", task.id)
            renewal_limit = now.date() + timedelta(days=30)
            leases = Lease.objects.filter(
                status="active",
                assigned_agent__isnull=False,
                end_date__range=(now.date(), renewal_limit),
                agency__is_active=True,
                agency__payment_status="paid",
            ).filter(
                Q(agency__subscription_expires_at__isnull=True)
                | Q(agency__subscription_expires_at__gt=now)
            ).select_related("assigned_agent", "property")
            for lease in leases.iterator():
                try:
                    _, was_created = Notification.objects.get_or_create(
                        user=lease.assigned_agent,
                        category="lease_renewal",
                        link=f"/leases?lease={lease.id}",
                        created_at__date=now.date(),
                        defaults={
                            "agency": lease.agency,
                            "title": "Lease renewal approaching",
                            "message": f"{lease.property.title} ends on {lease.end_date}",
                        },
                    )
                    created += int(was_created)
                except Exception:
                    failed += 1
                    logger.exception("Lease reminder failed for lease %s", lease.id)
            job.result = {"created": created, "failed": failed}
        self.stdout.write(self.style.SUCCESS(
            f"Created {created} task reminders; {failed} failed."
        ))
