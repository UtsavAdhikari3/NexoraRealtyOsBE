from django.conf import settings
from django.db import models
from django.utils import timezone

from agencies.models import Agency
from properties.models import Property


class Lead(models.Model):
    SOURCE_CHOICES = [
        ("website", "Website"),
        ("facebook", "Facebook"),
        ("instagram", "Instagram"),
        ("tiktok", "TikTok"),
        ("whatsapp", "WhatsApp"),
        ("viber", "Viber"),
        ("phone", "Phone Inquiry"),
        ("manual", "Manual"),
        ("referral", "Referral"),
        ("walk_in", "Walk In"),
        ("property_portal", "Property Portal"),
    ]

    STATUS_CHOICES = [
        ("new", "New"),
        ("contacted", "Contacted"),
        ("interested", "Interested"),
        ("site_visit_scheduled", "Site Visit Scheduled"),
        ("site_visit_completed", "Site Visit Completed"),
        ("negotiating", "Negotiating"),
        ("token_booking", "Token / Booking"),
        ("won", "Won"),
        ("lost", "Lost"),
        ("follow_up_later", "Follow Up Later"),
        ("archived", "Archived"),
    ]

    FOLLOW_UP_PENDING = "pending"
    FOLLOW_UP_COMPLETED = "completed"
    FOLLOW_UP_NONE = "none"

    FOLLOW_UP_STATUS_CHOICES = [
        (FOLLOW_UP_NONE, "None"),
        (FOLLOW_UP_PENDING, "Pending"),
        (FOLLOW_UP_COMPLETED, "Completed"),
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

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_leads",
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
    custom_data = models.JSONField(default=dict, blank=True)
    last_contacted_at = models.DateTimeField(null=True, blank=True)
    next_follow_up_at = models.DateTimeField(null=True, blank=True)
    follow_up_status = models.CharField(
        max_length=20,
        choices=FOLLOW_UP_STATUS_CHOICES,
        default=FOLLOW_UP_NONE,
    )
    lost_reason = models.CharField(max_length=255, blank=True)
    follow_up_reminder_sent_at = models.DateTimeField(null=True, blank=True)
    follow_up_reminder_error = models.TextField(blank=True)
    assigned_at = models.DateTimeField(null=True, blank=True)
    response_due_at = models.DateTimeField(null=True, blank=True)
    first_responded_at = models.DateTimeField(null=True, blank=True)
    assignment_responded_at = models.DateTimeField(null=True, blank=True)
    response_time_seconds = models.PositiveIntegerField(null=True, blank=True)
    last_agent_activity_at = models.DateTimeField(null=True, blank=True)
    escalated_at = models.DateTimeField(null=True, blank=True)
    neglect_alerted_at = models.DateTimeField(null=True, blank=True)
    reassigned_at = models.DateTimeField(null=True, blank=True)
    reassignment_count = models.PositiveSmallIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["agency", "status", "created_at"]),
            models.Index(fields=["agency", "assigned_agent", "status"]),
            models.Index(fields=["agency", "follow_up_status", "next_follow_up_at"]),
            models.Index(fields=["agency", "phone"]),
            models.Index(fields=["agency", "response_due_at", "first_responded_at"]),
            models.Index(fields=["agency", "assigned_agent", "last_agent_activity_at"]),
        ]

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
        ("viber", "Viber"),
        ("facebook", "Facebook"),
        ("instagram", "Instagram"),
        ("email", "Email"),
        ("sms", "SMS"),
        ("meeting", "Meeting"),
        ("walk_in", "Walk In"),
        ("property_portal", "Property Portal"),
        ("site_visit", "Site Visit"),
        ("note", "Note"),
        ("other", "Other"),
    ]

    DIRECTION_CHOICES = [
        ("inbound", "Inbound"),
        ("outbound", "Outbound"),
        ("internal", "Internal Note"),
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

    direction = models.CharField(
        max_length=20,
        choices=DIRECTION_CHOICES,
        default="internal",
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

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new and self.direction != "internal":
            Lead.objects.filter(pk=self.lead_id).update(
                last_contacted_at=self.created_at,
                updated_at=timezone.now(),
            )
        if is_new and self.direction == "outbound" and self.agent_id:
            from .automation import record_agent_response
            lead = Lead.objects.select_related("assigned_agent").get(pk=self.lead_id)
            record_agent_response(lead, self.agent, self.created_at)


class LeadStatusHistory(models.Model):
    lead = models.ForeignKey(
        Lead,
        on_delete=models.CASCADE,
        related_name="status_history",
    )
    agency = models.ForeignKey(
        Agency,
        on_delete=models.CASCADE,
        related_name="lead_status_history",
    )
    from_status = models.CharField(max_length=40, blank=True)
    to_status = models.CharField(max_length=40, choices=Lead.STATUS_CHOICES)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lead_status_changes",
    )
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.lead_id}: {self.from_status} -> {self.to_status}"


class LeadAutomationSettings(models.Model):
    FALLBACK_CHOICES = [
        ("listing_agent", "Listing Agent"),
        ("round_robin", "Round Robin"),
        ("unassigned", "Leave Unassigned"),
    ]

    agency = models.OneToOneField(
        Agency, on_delete=models.CASCADE, related_name="lead_automation_settings"
    )
    is_enabled = models.BooleanField(default=True)
    fallback_assignment = models.CharField(
        max_length=30, choices=FALLBACK_CHOICES, default="listing_agent"
    )
    max_active_leads_per_agent = models.PositiveIntegerField(default=50)
    response_sla_minutes = models.PositiveIntegerField(default=30)
    escalation_minutes = models.PositiveIntegerField(default=120)
    inactive_reassign_hours = models.PositiveIntegerField(default=48)
    manager_alert_hours = models.PositiveIntegerField(default=24)
    follow_up_reminder_hours = models.PositiveIntegerField(default=24)
    auto_reassign_inactive = models.BooleanField(default=True)
    auto_detect_duplicates = models.BooleanField(default=True)
    round_robin_last_agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="automation_round_robin_cursors",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class LeadAssignmentRule(models.Model):
    METHOD_CHOICES = [
        ("specific_agent", "Specific Agent"),
        ("listing_agent", "Listing Agent"),
        ("round_robin", "Round Robin"),
    ]

    agency = models.ForeignKey(
        Agency, on_delete=models.CASCADE, related_name="lead_assignment_rules"
    )
    name = models.CharField(max_length=120)
    priority = models.PositiveIntegerField(default=100)
    is_active = models.BooleanField(default=True)
    match_property = models.ForeignKey(
        Property, on_delete=models.CASCADE, null=True, blank=True,
        related_name="lead_assignment_rules",
    )
    match_location = models.CharField(max_length=255, blank=True)
    match_property_type = models.CharField(
        max_length=30, choices=Property.PROPERTY_TYPES, blank=True
    )
    assignment_method = models.CharField(
        max_length=30, choices=METHOD_CHOICES, default="round_robin"
    )
    assign_to_agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="lead_assignment_rules",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["priority", "id"]
        indexes = [models.Index(fields=["agency", "is_active", "priority"])]


class LeadDuplicateFlag(models.Model):
    STATUS_CHOICES = [
        ("pending", "Needs Review"),
        ("confirmed", "Confirmed Duplicate"),
        ("dismissed", "Not a Duplicate"),
    ]
    agency = models.ForeignKey(
        Agency, on_delete=models.CASCADE, related_name="lead_duplicate_flags"
    )
    lead = models.ForeignKey(
        Lead, on_delete=models.CASCADE, related_name="duplicate_flags"
    )
    candidate = models.ForeignKey(
        Lead, on_delete=models.CASCADE, related_name="duplicate_candidates"
    )
    score = models.PositiveSmallIntegerField(default=0)
    reasons = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_lead_duplicates",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-score", "-created_at"]
        constraints = [models.UniqueConstraint(
            fields=["lead", "candidate"], name="unique_lead_duplicate_pair"
        )]


class LeadAutomationEvent(models.Model):
    EVENT_CHOICES = [
        ("assigned", "Assigned"), ("response", "First Response"),
        ("duplicate", "Duplicate Flagged"), ("escalated", "Escalated"),
        ("neglect_alert", "Neglect Alert"), ("reassigned", "Reassigned"),
        ("follow_up_reminder", "Follow-up Reminder"),
    ]
    agency = models.ForeignKey(
        Agency, on_delete=models.CASCADE, related_name="lead_automation_events"
    )
    lead = models.ForeignKey(
        Lead, on_delete=models.CASCADE, related_name="automation_events"
    )
    event_type = models.CharField(max_length=30, choices=EVENT_CHOICES)
    rule = models.ForeignKey(
        LeadAssignmentRule, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="events",
    )
    from_agent = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="lead_automation_events_from",
    )
    to_agent = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="lead_automation_events_to",
    )
    summary = models.CharField(max_length=255)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["agency", "event_type", "created_at"])]
