from django.conf import settings
from django.db import models


class SocialPost(models.Model):
    PLATFORM_FACEBOOK = "facebook"
    PLATFORM_INSTAGRAM = "instagram"
    PLATFORM_TIKTOK = "tiktok"
    PLATFORM_YOUTUBE = "youtube"
    PLATFORM_LINKEDIN = "linkedin"

    PLATFORM_CHOICES = [
        (PLATFORM_FACEBOOK, "Facebook"),
        (PLATFORM_INSTAGRAM, "Instagram"),
        (PLATFORM_TIKTOK, "TikTok"),
        (PLATFORM_YOUTUBE, "YouTube"),
        (PLATFORM_LINKEDIN, "LinkedIn"),
    ]

    STATUS_DRAFT = "draft"
    STATUS_SCHEDULED = "scheduled"
    STATUS_PUBLISHED = "published"
    STATUS_PARTIAL = "partial"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_SCHEDULED, "Scheduled"),
        (STATUS_PUBLISHED, "Published"),
        (STATUS_PARTIAL, "Partially Published"),
        (STATUS_FAILED, "Failed"),
    ]

    agency = models.ForeignKey(
        "agencies.Agency",
        on_delete=models.CASCADE,
        related_name="social_posts",
    )

    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="social_posts",
    )
    social_account = models.ForeignKey(
        "SocialAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="posts",
    )

    platform = models.CharField(max_length=30, choices=PLATFORM_CHOICES)
    target_platforms = models.JSONField(default=list, blank=True)
    caption = models.TextField()

    image = models.ImageField(
        upload_to="social_posts/",
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
    )

    scheduled_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, null=True)
    external_post_id = models.CharField(max_length=255, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_social_posts",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.platform} - {self.status} - {self.agency.name}"
    
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


class SocialAccount(models.Model):
    PROVIDER_META = "meta"
    PROVIDER_TIKTOK = "tiktok"
    PROVIDER_LINKEDIN = "linkedin"

    PROVIDER_CHOICES = [
        (PROVIDER_META, "Meta"),
        (PROVIDER_TIKTOK, "TikTok"),
        (PROVIDER_LINKEDIN, "LinkedIn"),
    ]

    PLATFORM_FACEBOOK = "facebook"
    PLATFORM_INSTAGRAM = "instagram"
    PLATFORM_TIKTOK = "tiktok"
    PLATFORM_LINKEDIN = "linkedin"

    PLATFORM_CHOICES = [
        (PLATFORM_FACEBOOK, "Facebook"),
        (PLATFORM_INSTAGRAM, "Instagram"),
        (PLATFORM_TIKTOK, "TikTok"),
        (PLATFORM_LINKEDIN, "LinkedIn"),
    ]

    STATUS_CONNECTED = "connected"
    STATUS_DISCONNECTED = "disconnected"
    STATUS_EXPIRED = "expired"

    STATUS_CHOICES = [
        (STATUS_CONNECTED, "Connected"),
        (STATUS_DISCONNECTED, "Disconnected"),
        (STATUS_EXPIRED, "Expired"),
    ]

    agency = models.ForeignKey(
        "agencies.Agency",
        on_delete=models.CASCADE,
        related_name="social_accounts",
    )

    provider = models.CharField(max_length=30, choices=PROVIDER_CHOICES)
    platform = models.CharField(max_length=30, choices=PLATFORM_CHOICES)

    external_id = models.CharField(max_length=255)
    name = models.CharField(max_length=255, blank=True, null=True)
    username = models.CharField(max_length=255, blank=True, null=True)

    # For Instagram accounts connected through a Facebook Page
    page_id = models.CharField(max_length=255, blank=True, null=True)

    access_token = models.TextField()
    token_expires_at = models.DateTimeField(blank=True, null=True)
    webhook_subscription_status = models.CharField(max_length=30, blank=True)
    webhook_subscribed_at = models.DateTimeField(null=True, blank=True)
    webhook_error = models.TextField(blank=True)

    scopes = models.TextField(blank=True, null=True)
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default=STATUS_CONNECTED,
    )

    connected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="connected_social_accounts",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (
            "agency",
            "provider",
            "platform",
            "external_id",
        )
        ordering = ["platform", "name"]

    def __str__(self):
        return f"{self.agency.name} - {self.platform} - {self.name or self.external_id}"


class SocialOAuthState(models.Model):
    provider = models.CharField(max_length=30)
    state = models.CharField(max_length=255, unique=True)

    agency = models.ForeignKey(
        "agencies.Agency",
        on_delete=models.CASCADE,
        related_name="social_oauth_states",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="social_oauth_states",
    )

    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def create_state(cls, provider, agency, user):
        return cls.objects.create(
            provider=provider,
            agency=agency,
            user=user,
            state=secrets.token_urlsafe(48),
            expires_at=timezone.now() + timezone.timedelta(minutes=10),
        )

    @property
    def is_valid(self):
        return self.used_at is None and self.expires_at > timezone.now()

    def mark_used(self):
        self.used_at = timezone.now()
        self.save(update_fields=["used_at"])


class SocialPublishResult(models.Model):
    STATUS_PENDING = "pending"
    STATUS_PUBLISHED = "published"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PUBLISHED, "Published"),
        (STATUS_FAILED, "Failed"),
    ]

    post = models.ForeignKey(
        SocialPost,
        on_delete=models.CASCADE,
        related_name="publish_results",
    )
    social_account = models.ForeignKey(
        SocialAccount,
        on_delete=models.CASCADE,
        related_name="publish_results",
    )
    platform = models.CharField(max_length=30, choices=SocialAccount.PLATFORM_CHOICES)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    container_id = models.CharField(max_length=255, blank=True)
    external_post_id = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)
    attempt_count = models.PositiveIntegerField(default=0)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["post", "social_account"],
                name="unique_social_publish_target",
            )
        ]
        ordering = ["platform", "id"]


SOCIAL_POST_PLATFORM_CHOICES = SocialPost.PLATFORM_CHOICES
SOCIAL_ACCOUNT_PLATFORM_CHOICES = SocialAccount.PLATFORM_CHOICES
