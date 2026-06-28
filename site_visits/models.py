from django.conf import settings
from django.db import models

from agencies.models import Agency
from leads.models import Lead
from properties.models import Property


class SiteVisit(models.Model):
    STATUS_CHOICES = [
        ("requested", "Requested"),
        ("scheduled", "Scheduled"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
        ("no_show", "No Show"),
        ("rescheduled", "Rescheduled"),
    ]

    agency = models.ForeignKey(
        Agency,
        on_delete=models.CASCADE,
        related_name="site_visits"
    )

    lead = models.ForeignKey(
        Lead,
        on_delete=models.CASCADE,
        related_name="site_visits"
    )

    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="site_visits"
    )

    assigned_agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_site_visits"
    )

    scheduled_at = models.DateTimeField()
    scheduled_email_sent_at = models.DateTimeField(
        null=True,
        blank=True
    )
    scheduled_email_error = models.TextField(blank=True)
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default="scheduled"
    )

    notes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_site_visits"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-scheduled_at"]

    def __str__(self):
        return f"{self.lead.full_name} - {self.property.title} - {self.scheduled_at}"