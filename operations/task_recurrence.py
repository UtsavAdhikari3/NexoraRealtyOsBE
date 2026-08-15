import calendar
from datetime import timedelta

from django.db import transaction

from .models import Notification, Task


def next_due_at(due_at, recurrence):
    if recurrence == "daily":
        return due_at + timedelta(days=1)
    if recurrence == "weekly":
        return due_at + timedelta(weeks=1)
    if recurrence == "monthly":
        year = due_at.year + (1 if due_at.month == 12 else 0)
        month = 1 if due_at.month == 12 else due_at.month + 1
        day = min(due_at.day, calendar.monthrange(year, month)[1])
        return due_at.replace(year=year, month=month, day=day)
    return None


@transaction.atomic
def create_next_task_occurrence(task):
    """Create exactly one next occurrence for a completed recurring task."""
    task = Task.objects.select_for_update().get(pk=task.pk)
    if task.status != "done" or not task.recurrence or not task.due_at:
        return None, False

    due_at = next_due_at(task.due_at, task.recurrence)
    if due_at is None:
        return None, False

    next_task, created = Task.objects.get_or_create(
        generated_from=task,
        defaults={
            "agency": task.agency,
            "title": task.title,
            "description": task.description,
            "status": "todo",
            "priority": task.priority,
            "due_at": due_at,
            "assigned_to": task.assigned_to,
            "created_by": task.created_by,
            "lead": task.lead,
            "deal": task.deal,
            "property": task.property,
            "recurrence": task.recurrence,
        },
    )
    if created and next_task.assigned_to:
        Notification.objects.create(
            agency=next_task.agency,
            user=next_task.assigned_to,
            title="Recurring task created",
            message=f"{next_task.title} is due {next_task.due_at:%Y-%m-%d %H:%M}",
            category="task",
            link=f"/tasks?task={next_task.id}",
        )
    return next_task, created
