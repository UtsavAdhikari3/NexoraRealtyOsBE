from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
import uuid

from .subdomains import RESERVED_SUBDOMAINS, generated_agency_subdomain, normalize_subdomain


class Agency(models.Model):
    WEBSITE_ONBOARDING_NOT_STARTED = "not_started"
    WEBSITE_ONBOARDING_IN_PROGRESS = "in_progress"
    WEBSITE_ONBOARDING_READY = "ready"
    WEBSITE_ONBOARDING_COMPLETED = "completed"
    WEBSITE_ONBOARDING_STATUS_CHOICES = [
        (WEBSITE_ONBOARDING_NOT_STARTED, "Not started"),
        (WEBSITE_ONBOARDING_IN_PROGRESS, "In progress"),
        (WEBSITE_ONBOARDING_READY, "Ready to publish"),
        (WEBSITE_ONBOARDING_COMPLETED, "Completed"),
    ]
    LANGUAGE_ENGLISH = "en"
    LANGUAGE_NEPALI = "ne"
    LANGUAGE_CHOICES = [
        (LANGUAGE_ENGLISH, "English"),
        (LANGUAGE_NEPALI, "नेपाली"),
    ]
    DATE_SYSTEM_AD = "ad"
    DATE_SYSTEM_BS = "bs"
    DATE_SYSTEM_CHOICES = [
        (DATE_SYSTEM_AD, "Anno Domini (AD)"),
        (DATE_SYSTEM_BS, "Bikram Sambat (BS)"),
    ]
    PAYMENT_UNPAID = "unpaid"
    PAYMENT_PENDING = "pending"
    PAYMENT_PAID = "paid"
    PAYMENT_EXPIRED = "expired"
    PAYMENT_CANCELLED = "cancelled"

    PAYMENT_STATUS_CHOICES = [
        (PAYMENT_UNPAID, "Unpaid"),
        (PAYMENT_PENDING, "Pending"),
        (PAYMENT_PAID, "Paid"),
        (PAYMENT_EXPIRED, "Expired"),
        (PAYMENT_CANCELLED, "Cancelled"),
    ]

    name = models.CharField(max_length=255)
    license_number = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=180, unique=True, blank=True, null=True)

    logo = models.ImageField(upload_to="agency_branding/logos/", blank=True, null=True)
    cover_image = models.ImageField(
        upload_to="agency_branding/covers/",
        blank=True,
        null=True,
    )
    about = models.TextField(blank=True)
    address = models.TextField(blank=True)
    province = models.CharField(max_length=100, blank=True)
    district = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    municipality = models.CharField(max_length=150, blank=True)
    ward_number = models.CharField(max_length=20, blank=True)
    tole = models.CharField(max_length=150, blank=True)
    business_hours = models.CharField(max_length=255, blank=True)
    primary_color = models.CharField(max_length=20, blank=True)
    seo_title = models.CharField(max_length=70, blank=True)
    seo_description = models.CharField(max_length=180, blank=True)
    custom_domain = models.CharField(max_length=255, blank=True)
    website_template = models.CharField(max_length=80, default="luxury-agency")
    website_config = models.JSONField(default=dict, blank=True)
    website_draft_config = models.JSONField(default=dict, blank=True)
    website_published_config = models.JSONField(default=dict, blank=True)
    website_onboarding_status = models.CharField(
        max_length=20,
        choices=WEBSITE_ONBOARDING_STATUS_CHOICES,
        default=WEBSITE_ONBOARDING_NOT_STARTED,
    )
    website_onboarding_step = models.PositiveSmallIntegerField(default=1)
    website_completion_percentage = models.PositiveSmallIntegerField(default=0)
    website_config_version = models.PositiveIntegerField(default=0)
    website_draft_revision = models.PositiveIntegerField(default=0)
    website_draft_updated_at = models.DateTimeField(null=True, blank=True)
    website_draft_updated_by = models.ForeignKey(
        "users.AgencyUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="website_drafts_updated",
    )
    website_onboarding_completed_at = models.DateTimeField(null=True, blank=True)
    website_published_at = models.DateTimeField(null=True, blank=True)
    default_language = models.CharField(
        max_length=2, choices=LANGUAGE_CHOICES, default=LANGUAGE_ENGLISH
    )
    default_date_system = models.CharField(
        max_length=2, choices=DATE_SYSTEM_CHOICES, default=DATE_SYSTEM_AD
    )
    use_nepali_digits = models.BooleanField(default=False)
    timezone = models.CharField(max_length=50, default="Asia/Kathmandu")
    message_templates = models.JSONField(default=dict, blank=True)
    # Keep programmatic/admin-created agencies backward compatible. The public
    # registration flow explicitly creates agencies as unpublished until their
    # onboarding checklist is complete.
    is_website_published = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    subscription_expires_at = models.DateTimeField(null=True, blank=True)

    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    facebook_url = models.URLField(max_length=500, blank=True, null=True)
    instagram_url = models.URLField(max_length=500, blank=True, null=True)
    tiktok_url = models.URLField(max_length=500, blank=True, null=True)
    youtube_url = models.URLField(max_length=500, blank=True, null=True)
    linkedin_url = models.URLField(max_length=500, blank=True, null=True)

    whatsapp_number = models.CharField(max_length=30, blank=True, null=True)
    viber_number = models.CharField(max_length=30, blank=True, null=True)
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default=PAYMENT_UNPAID
    )

    paid_at = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def mark_paid(self):
        self.payment_status = self.PAYMENT_PAID
        self.paid_at = timezone.now()
        self.save(
            update_fields=[
                "payment_status",
                "paid_at",
            ]
        )

    @property
    def has_active_subscription(self):
        if not self.is_active or self.payment_status != self.PAYMENT_PAID:
            return False

        if self.subscription_expires_at is None:
            return True

        return self.subscription_expires_at > timezone.now()

    def save(self, *args, **kwargs):
        if not self.slug:
            # Public registration validates that the agency name itself produces
            # a usable subdomain. Keep direct/internal agency creation compatible
            # with non-Latin names by falling back to the unique licence number.
            self.slug = generated_agency_subdomain(self.name) or normalize_subdomain(
                self.license_number
            )
        else:
            self.slug = normalize_subdomain(self.slug)
        if not self.slug:
            raise ValidationError({"name": "Agency name must contain letters or numbers for its website subdomain."})
        if self.slug in RESERVED_SUBDOMAINS:
            raise ValidationError({"name": f"The {self.slug} subdomain is reserved by Nexora."})

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class WebsiteVersion(models.Model):
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="website_versions")
    version = models.PositiveIntegerField()
    template_key = models.CharField(max_length=80)
    schema_version = models.PositiveIntegerField(default=2)
    config = models.JSONField()
    published_at = models.DateTimeField(auto_now_add=True)
    published_by = models.ForeignKey(
        "users.AgencyUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="website_versions_published",
    )
    restored_from = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="restored_versions",
    )

    class Meta:
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(fields=["agency", "version"], name="unique_agency_website_version"),
        ]

    def __str__(self):
        return f"{self.agency} website v{self.version}"


class AgencyDomain(models.Model):
    STATUS_PENDING = "pending"
    STATUS_VERIFIED = "verified"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending verification"),
        (STATUS_VERIFIED, "Verified"),
        (STATUS_FAILED, "Verification failed"),
    ]

    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="website_domains")
    domain = models.CharField(max_length=253, unique=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    verification_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    is_active = models.BooleanField(default=False)
    is_primary = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_primary", "domain"]
        constraints = [
            models.UniqueConstraint(
                fields=["agency"],
                condition=models.Q(is_primary=True),
                name="unique_primary_domain_per_agency",
            ),
        ]
        indexes = [
            models.Index(fields=["domain", "status", "is_active"], name="agency_domain_lookup_idx"),
        ]

    def __str__(self):
        return self.domain
