from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from operations.models import Lease, Notification, Task


class Command(BaseCommand):
    help = "Create in-app reminders for tasks due in the next 24 hours."

    def handle(self, *args, **options):
        now = timezone.now()
        tasks = Task.objects.filter(
            status__in=["todo", "in_progress"],
            assigned_to__isnull=False,
            due_at__range=(now, now + timedelta(hours=24)),
        )
        created = 0
        for task in tasks:
            exists = Notification.objects.filter(
                user=task.assigned_to,
                category="task_due",
                link=f"/tasks?task={task.id}",
                created_at__date=now.date(),
            ).exists()
            if not exists:
                Notification.objects.create(
                    agency=task.agency,
                    user=task.assigned_to,
                    title="Task due soon",
                    message=task.title,
                    category="task_due",
                    link=f"/tasks?task={task.id}",
                )
                created += 1
        renewal_limit = now.date() + timedelta(days=30)
        leases = Lease.objects.filter(
            status="active",
            assigned_agent__isnull=False,
            end_date__range=(now.date(), renewal_limit),
        ).select_related("assigned_agent", "property")
        for lease in leases:
            exists = Notification.objects.filter(
                user=lease.assigned_agent,
                category="lease_renewal",
                link=f"/leases?lease={lease.id}",
                created_at__date=now.date(),
            ).exists()
            if not exists:
                Notification.objects.create(
                    agency=lease.agency,
                    user=lease.assigned_agent,
                    title="Lease renewal approaching",
                    message=f"{lease.property.title} ends on {lease.end_date}",
                    category="lease_renewal",
                    link=f"/leases?lease={lease.id}",
                )
                created += 1
        self.stdout.write(self.style.SUCCESS(f"Created {created} task reminders."))
