import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from agencies.models import Agency
from leads.models import Lead
from properties.models import Property

INVITATION_ROLE_CHOICES = [
    ("agency_manager", "Agency Manager"),
    ("agent", "Agent"),
]


class AgencyScopedModel(models.Model):
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Contact(AgencyScopedModel):
    TYPE_CHOICES = [
        ("buyer", "Buyer"), ("seller", "Seller"), ("tenant", "Tenant"),
        ("landlord", "Landlord"), ("investor", "Investor"),
        ("vendor", "Vendor"), ("other", "Other"),
    ]
    full_name = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    contact_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default="buyer")
    company = models.CharField(max_length=255, blank=True)
    address = models.TextField(blank=True)
    source = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)
    tags = models.JSONField(default=list, blank=True)
    custom_data = models.JSONField(default=dict, blank=True)
    lead = models.OneToOneField(Lead, on_delete=models.SET_NULL, null=True, blank=True, related_name="contact")
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_contacts")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["full_name"]
        indexes = [models.Index(fields=["agency", "contact_type", "is_active"])]

    def __str__(self):
        return self.full_name


class Owner(AgencyScopedModel):
    full_name = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30)
    address = models.TextField(blank=True)
    tax_id = models.CharField(max_length=100, blank=True)
    bank_details = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    custom_data = models.JSONField(default=dict, blank=True)
    contact = models.OneToOneField(Contact, on_delete=models.SET_NULL, null=True, blank=True, related_name="owner_profile")
    properties = models.ManyToManyField(Property, blank=True, related_name="owners")

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name


class Deal(AgencyScopedModel):
    STAGES = [
        ("qualified", "Qualified"), ("offer", "Offer"),
        ("negotiation", "Negotiation"), ("token", "Token / Booking"),
        ("contract", "Contract"), ("closed_won", "Closed Won"),
        ("closed_lost", "Closed Lost"),
    ]
    title = models.CharField(max_length=255)
    lead = models.ForeignKey(Lead, on_delete=models.SET_NULL, null=True, blank=True, related_name="deals")
    contact = models.ForeignKey(Contact, on_delete=models.SET_NULL, null=True, blank=True, related_name="deals")
    property = models.ForeignKey(Property, on_delete=models.SET_NULL, null=True, blank=True, related_name="deals")
    assigned_agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_deals")
    stage = models.CharField(max_length=30, choices=STAGES, default="qualified")
    value = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    token_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    commission_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    commission_rate = models.DecimalField(max_digits=6, decimal_places=3, default=0)
    currency = models.CharField(max_length=10, default="NPR")
    expected_close_date = models.DateField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    lost_reason = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    custom_data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["agency", "stage", "expected_close_date"])]

    def save(self, *args, **kwargs):
        if self.stage == "closed_won" and not self.closed_at:
            self.closed_at = timezone.now()
        elif self.stage not in {"closed_won", "closed_lost"}:
            self.closed_at = None
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class Offer(AgencyScopedModel):
    STATUS_CHOICES = [
        ("draft", "Draft"), ("submitted", "Submitted"), ("countered", "Countered"),
        ("accepted", "Accepted"), ("rejected", "Rejected"), ("withdrawn", "Withdrawn"),
        ("expired", "Expired"),
    ]
    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, related_name="offers")
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    currency = models.CharField(max_length=10, default="NPR")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    terms = models.TextField(blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="submitted_offers")
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class Document(AgencyScopedModel):
    CATEGORY_CHOICES = [
        ("identity", "Identity"), ("ownership", "Ownership"), ("contract", "Contract"),
        ("receipt", "Receipt"), ("floor_plan", "Floor Plan"), ("other", "Other"),
    ]
    title = models.CharField(max_length=255)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default="other")
    file = models.FileField(upload_to="documents/")
    description = models.TextField(blank=True)
    property = models.ForeignKey(Property, on_delete=models.CASCADE, null=True, blank=True, related_name="documents")
    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, null=True, blank=True, related_name="documents")
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, null=True, blank=True, related_name="documents")
    owner = models.ForeignKey(Owner, on_delete=models.CASCADE, null=True, blank=True, related_name="documents")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="uploaded_documents")
    is_customer_visible = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]


class Lease(AgencyScopedModel):
    STATUS_CHOICES = [("draft", "Draft"), ("active", "Active"), ("expired", "Expired"), ("terminated", "Terminated"), ("renewed", "Renewed")]
    property = models.ForeignKey(Property, on_delete=models.PROTECT, related_name="leases")
    tenant = models.ForeignKey(Contact, on_delete=models.PROTECT, related_name="tenant_leases")
    owner = models.ForeignKey(Owner, on_delete=models.SET_NULL, null=True, blank=True, related_name="leases")
    assigned_agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_leases")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    monthly_rent = models.DecimalField(max_digits=14, decimal_places=2)
    security_deposit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    currency = models.CharField(max_length=10, default="NPR")
    start_date = models.DateField()
    end_date = models.DateField()
    renewal_reminder_at = models.DateField(null=True, blank=True)
    payment_day = models.PositiveSmallIntegerField(default=1)
    terms = models.TextField(blank=True)
    custom_data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-start_date"]


class Task(AgencyScopedModel):
    STATUS_CHOICES = [("todo", "To Do"), ("in_progress", "In Progress"), ("done", "Done"), ("cancelled", "Cancelled")]
    PRIORITIES = [("low", "Low"), ("medium", "Medium"), ("high", "High"), ("urgent", "Urgent")]
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="todo")
    priority = models.CharField(max_length=20, choices=PRIORITIES, default="medium")
    due_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_tasks")
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, null=True, blank=True, related_name="tasks")
    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, null=True, blank=True, related_name="tasks")
    property = models.ForeignKey(Property, on_delete=models.CASCADE, null=True, blank=True, related_name="tasks")
    recurrence = models.CharField(max_length=30, blank=True)

    class Meta:
        ordering = ["status", "due_at"]
        indexes = [models.Index(fields=["agency", "assigned_to", "status", "due_at"])]

    def save(self, *args, **kwargs):
        if self.status == "done" and not self.completed_at:
            self.completed_at = timezone.now()
        elif self.status != "done":
            self.completed_at = None
        super().save(*args, **kwargs)


class Notification(models.Model):
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="notifications")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=255)
    message = models.TextField(blank=True)
    category = models.CharField(max_length=40, default="system")
    link = models.CharField(max_length=500, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "is_read", "created_at"])]


class Invitation(models.Model):
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField()
    full_name = models.CharField(max_length=255)
    role = models.CharField(
        max_length=50,
        choices=INVITATION_ROLE_CHOICES,
        default="agent",
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="sent_invitations")
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    delivery_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["agency", "email"], condition=models.Q(accepted_at__isnull=True), name="unique_pending_agency_invite")]


class CustomFieldDefinition(AgencyScopedModel):
    MODULE_CHOICES = [(name, name.title()) for name in ["lead", "contact", "property", "deal", "owner", "lease"]]
    FIELD_TYPES = [(name, name.title()) for name in ["text", "number", "date", "boolean", "select", "multiselect"]]
    module = models.CharField(max_length=30, choices=MODULE_CHOICES)
    key = models.SlugField(max_length=80)
    label = models.CharField(max_length=120)
    field_type = models.CharField(max_length=20, choices=FIELD_TYPES, default="text")
    options = models.JSONField(default=list, blank=True)
    is_required = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["module", "sort_order", "label"]
        constraints = [models.UniqueConstraint(fields=["agency", "module", "key"], name="unique_agency_module_custom_field")]


class PipelineStage(AgencyScopedModel):
    MODULE_CHOICES = [("lead", "Lead"), ("deal", "Deal")]
    module = models.CharField(max_length=20, choices=MODULE_CHOICES)
    key = models.SlugField(max_length=50)
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=20, default="#496B5A")
    sort_order = models.PositiveIntegerField(default=0)
    is_closed = models.BooleanField(default=False)
    is_won = models.BooleanField(default=False)

    class Meta:
        ordering = ["module", "sort_order"]
        constraints = [models.UniqueConstraint(fields=["agency", "module", "key"], name="unique_agency_pipeline_stage")]


class AuditLog(models.Model):
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="audit_logs")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="audit_logs")
    action = models.CharField(max_length=30)
    entity_type = models.CharField(max_length=80)
    entity_id = models.CharField(max_length=80)
    summary = models.CharField(max_length=255)
    changes = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["agency", "entity_type", "created_at"])]


class CustomerProfile(AgencyScopedModel):
    email = models.EmailField()
    full_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=30, blank=True)
    access_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    password_hash = models.CharField(max_length=255, default="!")
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["agency", "email"], name="unique_agency_customer")]

    def set_password(self, raw_password):
        from django.contrib.auth.hashers import make_password
        self.password_hash = make_password(raw_password)

    def check_password(self, raw_password):
        from django.contrib.auth.hashers import check_password
        return check_password(raw_password, self.password_hash)


class SavedProperty(models.Model):
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="saved_properties")
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="saved_by_customers")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["customer", "property"], name="unique_customer_saved_property")]


class SavedSearch(AgencyScopedModel):
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="saved_searches")
    name = models.CharField(max_length=120)
    filters = models.JSONField(default=dict)
    alerts_enabled = models.BooleanField(default=True)
    last_notified_at = models.DateTimeField(null=True, blank=True)


class AppointmentAvailability(AgencyScopedModel):
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="appointment_availability")
    weekday = models.PositiveSmallIntegerField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    slot_minutes = models.PositiveSmallIntegerField(default=30)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["weekday", "start_time"]
        constraints = [models.UniqueConstraint(fields=["agent", "weekday", "start_time"], name="unique_agent_availability_start")]


class Appointment(AgencyScopedModel):
    STATUS_CHOICES = [("requested", "Requested"), ("confirmed", "Confirmed"), ("completed", "Completed"), ("cancelled", "Cancelled")]
    customer = models.ForeignKey(CustomerProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="appointments")
    property = models.ForeignKey(Property, on_delete=models.SET_NULL, null=True, blank=True, related_name="appointments")
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="appointments")
    full_name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="requested")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["starts_at"]


class SubscriptionPlan(models.Model):
    name = models.CharField(max_length=100)
    code = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    price_monthly = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default="USD")
    features = models.JSONField(default=list, blank=True)
    max_agents = models.PositiveIntegerField(default=5)
    max_properties = models.PositiveIntegerField(default=100)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Subscription(models.Model):
    STATUS_CHOICES = [("trialing", "Trialing"), ("active", "Active"), ("past_due", "Past Due"), ("cancelled", "Cancelled"), ("expired", "Expired")]
    agency = models.OneToOneField(Agency, on_delete=models.CASCADE, related_name="subscription")
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="trialing")
    provider = models.CharField(max_length=30, default="stripe")
    provider_customer_id = models.CharField(max_length=255, blank=True)
    provider_subscription_id = models.CharField(max_length=255, blank=True)
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Payment(models.Model):
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10)
    status = models.CharField(max_length=30)
    provider_payment_id = models.CharField(max_length=255, blank=True)
    receipt_url = models.URLField(blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
