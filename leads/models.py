from django.conf import settings
from django.db import models

from agencies.models import Agency
from properties.models import Property


class Lead(models.Model):
    SOURCE_CHOICES = [
        ("website", "Website"),
        ("facebook", "Facebook"),
        ("instagram", "Instagram"),
        ("tiktok", "TikTok"),
        ("whatsapp", "WhatsApp"),
        ("manual", "Manual"),
        ("referral", "Referral"),
        ("walk_in", "Walk In"),
    ]

    STATUS_CHOICES = [
        ("new", "New"),
        ("contacted", "Contacted"),
        ("interested", "Interested"),
        ("site_visit_scheduled", "Site Visit Scheduled"),
        ("negotiating", "Negotiating"),
        ("won", "Won"),
        ("lost", "Lost"),
        ("archived", "Archived"),
    ]

    agency = models.ForeignKey(
        Agency,
        on_delete=models.CASCADE,
        related_name="leads"
    )

    assigned_agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_leads"
    )

    full_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=30)
    email = models.EmailField(blank=True)

    source = models.CharField(
        max_length=30,
        choices=SOURCE_CHOICES,
        default="manual"
    )

    status = models.CharField(
        max_length=40,
        choices=STATUS_CHOICES,
        default="new"
    )

    budget_min = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True
    )

    budget_max = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True
    )

    preferred_location = models.CharField(
        max_length=255,
        blank=True
    )

    purpose = models.CharField(
        max_length=20,
        choices=Property.PURPOSES,
        blank=True
    )

    property_type = models.CharField(
        max_length=30,
        choices=Property.PROPERTY_TYPES,
        blank=True
    )

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.full_name} - {self.phone}"


class LeadPropertyInterest(models.Model):
    INTEREST_LEVEL_CHOICES = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("hot", "Hot"),
    ]

    agency = models.ForeignKey(
        Agency,
        on_delete=models.CASCADE,
        related_name="lead_property_interests"
    )

    lead = models.ForeignKey(
        Lead,
        on_delete=models.CASCADE,
        related_name="property_interests"
    )

    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="lead_interests"
    )

    interest_level = models.CharField(
        max_length=20,
        choices=INTEREST_LEVEL_CHOICES,
        default="medium"
    )

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["lead", "property"],
                name="unique_lead_property_interest"
            )
        ]

    def __str__(self):
        return f"{self.lead.full_name} interested in {self.property.title}"


class LeadInteraction(models.Model):
    INTERACTION_TYPE_CHOICES = [
        ("call", "Call"),
        ("whatsapp", "WhatsApp"),
        ("email", "Email"),
        ("meeting", "Meeting"),
        ("site_visit", "Site Visit"),
        ("note", "Note"),
    ]

    agency = models.ForeignKey(
        Agency,
        on_delete=models.CASCADE,
        related_name="lead_interactions"
    )

    lead = models.ForeignKey(
        Lead,
        on_delete=models.CASCADE,
        related_name="interactions"
    )

    agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lead_interactions"
    )

    interaction_type = models.CharField(
        max_length=30,
        choices=INTERACTION_TYPE_CHOICES,
        default="note"
    )

    note = models.TextField()

    follow_up_date = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.lead.full_name} - {self.interaction_type}"