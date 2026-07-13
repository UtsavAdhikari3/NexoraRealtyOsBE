from django.conf import settings
from django.db import models


class SocialContact(models.Model):
    agency = models.ForeignKey(
        "agencies.Agency",
        on_delete=models.CASCADE,
        related_name="social_contacts",
    )
    social_account = models.ForeignKey(
        "social_media.SocialAccount",
        on_delete=models.CASCADE,
        related_name="contacts",
    )
    platform = models.CharField(max_length=30)
    external_user_id = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255, blank=True)
    username = models.CharField(max_length=255, blank=True)
    profile_image_url = models.URLField(max_length=1000, blank=True)
    linked_lead = models.ForeignKey(
        "leads.Lead",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="social_contacts",
    )
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["social_account", "external_user_id"],
                name="unique_social_contact_per_account",
            )
        ]
        indexes = [
            models.Index(fields=["agency", "platform", "last_seen_at"]),
        ]

    def __str__(self):
        return self.display_name or self.username or self.external_user_id


class Conversation(models.Model):
    STATUS_OPEN = "open"
    STATUS_PENDING = "pending"
    STATUS_CLOSED = "closed"
    STATUS_SPAM = "spam"

    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_PENDING, "Pending"),
        (STATUS_CLOSED, "Closed"),
        (STATUS_SPAM, "Spam"),
    ]

    agency = models.ForeignKey(
        "agencies.Agency",
        on_delete=models.CASCADE,
        related_name="inbox_conversations",
    )
    social_account = models.ForeignKey(
        "social_media.SocialAccount",
        on_delete=models.CASCADE,
        related_name="conversations",
    )
    contact = models.ForeignKey(
        SocialContact,
        on_delete=models.CASCADE,
        related_name="conversations",
    )
    platform = models.CharField(max_length=30)
    external_conversation_id = models.CharField(max_length=255)
    assigned_agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_inbox_conversations",
    )
    linked_lead = models.ForeignKey(
        "leads.Lead",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inbox_conversations",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_OPEN,
    )
    unread_count = models.PositiveIntegerField(default=0)
    last_message_at = models.DateTimeField(null=True, blank=True)
    last_message_preview = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["social_account", "external_conversation_id"],
                name="unique_external_conversation_per_account",
            )
        ]
        ordering = ["-last_message_at", "-updated_at"]
        indexes = [
            models.Index(fields=["agency", "status", "last_message_at"]),
            models.Index(fields=["agency", "assigned_agent", "status"]),
        ]

    def __str__(self):
        return f"{self.platform}: {self.contact}"


class SocialMessage(models.Model):
    DIRECTION_INBOUND = "inbound"
    DIRECTION_OUTBOUND = "outbound"
    DIRECTION_CHOICES = [
        (DIRECTION_INBOUND, "Inbound"),
        (DIRECTION_OUTBOUND, "Outbound"),
    ]

    TYPE_TEXT = "text"
    TYPE_IMAGE = "image"
    TYPE_VIDEO = "video"
    TYPE_AUDIO = "audio"
    TYPE_FILE = "file"
    TYPE_STICKER = "sticker"
    TYPE_POSTBACK = "postback"
    TYPE_UNSUPPORTED = "unsupported"

    TYPE_CHOICES = [
        (TYPE_TEXT, "Text"),
        (TYPE_IMAGE, "Image"),
        (TYPE_VIDEO, "Video"),
        (TYPE_AUDIO, "Audio"),
        (TYPE_FILE, "File"),
        (TYPE_STICKER, "Sticker"),
        (TYPE_POSTBACK, "Postback"),
        (TYPE_UNSUPPORTED, "Unsupported"),
    ]

    STATUS_RECEIVED = "received"
    STATUS_PENDING = "pending"
    STATUS_SENT = "sent"
    STATUS_DELIVERED = "delivered"
    STATUS_READ = "read"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_RECEIVED, "Received"),
        (STATUS_PENDING, "Pending"),
        (STATUS_SENT, "Sent"),
        (STATUS_DELIVERED, "Delivered"),
        (STATUS_READ, "Read"),
        (STATUS_FAILED, "Failed"),
    ]

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    social_account = models.ForeignKey(
        "social_media.SocialAccount",
        on_delete=models.CASCADE,
        related_name="messages",
    )
    provider_message_id = models.CharField(max_length=255)
    direction = models.CharField(max_length=20, choices=DIRECTION_CHOICES)
    message_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default=TYPE_TEXT,
    )
    sender_external_id = models.CharField(max_length=255, blank=True)
    text = models.TextField(blank=True)
    attachments = models.JSONField(default=list, blank=True)
    delivery_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_RECEIVED,
    )
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["social_account", "provider_message_id"],
                name="unique_provider_message_per_account",
            )
        ]
        ordering = ["sent_at", "id"]
        indexes = [
            models.Index(fields=["conversation", "sent_at"]),
        ]


class WebhookEvent(models.Model):
    STATUS_RECEIVED = "received"
    STATUS_PROCESSED = "processed"
    STATUS_FAILED = "failed"

    provider = models.CharField(max_length=30, default="meta")
    object_type = models.CharField(max_length=50, blank=True)
    payload_hash = models.CharField(max_length=64, unique=True)
    raw_payload = models.JSONField()
    status = models.CharField(max_length=20, default=STATUS_RECEIVED)
    attempts = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-received_at"]
