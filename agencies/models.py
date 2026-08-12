from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class Agency(models.Model):
    WEBSITE_ONBOARDING_NOT_STARTED = "not_started"
    WEBSITE_ONBOARDING_IN_PROGRESS = "in_progress"
    WEBSITE_ONBOARDING_COMPLETED = "completed"
    WEBSITE_ONBOARDING_STATUS_CHOICES = [
        (WEBSITE_ONBOARDING_NOT_STARTED, "Not started"),
        (WEBSITE_ONBOARDING_IN_PROGRESS, "In progress"),
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
    website_onboarding_status = models.CharField(
        max_length=20,
        choices=WEBSITE_ONBOARDING_STATUS_CHOICES,
        default=WEBSITE_ONBOARDING_NOT_STARTED,
    )
    website_onboarding_step = models.PositiveSmallIntegerField(default=1)
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
            self.slug = slugify(f"{self.name}-{self.license_number}")[:180]

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name
