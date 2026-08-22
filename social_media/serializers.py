import json

from django.db import transaction
from django.utils import timezone
from PIL import Image, UnidentifiedImageError
from rest_framework import serializers

from properties.models import Property
from .models import (
    SOCIAL_PUBLISH_PLATFORM_CHOICES,
    SocialAccount,
    SocialConnectionSession,
    SocialPost,
    SocialPostMedia,
    SocialPublishResult,
)
from .services.video import ReelValidationError, compress_reel_upload


class MultipartListField(serializers.ListField):
    """Accept repeated multipart keys as a regular serializer list."""

    def get_value(self, dictionary):
        if hasattr(dictionary, "getlist"):
            values = dictionary.getlist(self.field_name)
            if values:
                return values
        return super().get_value(dictionary)


class MultipartJSONField(serializers.JSONField):
    """Decode JSON strings sent inside multipart form data."""

    def to_internal_value(self, data):
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (TypeError, ValueError) as exc:
                raise serializers.ValidationError("Enter valid JSON.") from exc
        return super().to_internal_value(data)


class SocialPostMediaSerializer(serializers.ModelSerializer):
    class Meta:
        model = SocialPostMedia
        fields = ["id", "image", "position"]
        read_only_fields = fields


class SocialPublishResultSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source="social_account.name", read_only=True)

    class Meta:
        model = SocialPublishResult
        fields = [
            "id",
            "social_account",
            "account_name",
            "platform",
            "status",
            "container_id",
            "external_post_id",
            "external_media_id",
            "error_message",
            "attempt_count",
            "published_at",
            "updated_at",
        ]


class SocialPostSerializer(serializers.ModelSerializer):
    property_title = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    publish_results = SocialPublishResultSerializer(many=True, read_only=True)
    media = SocialPostMediaSerializer(
        source="media_items",
        many=True,
        read_only=True,
    )
    images = MultipartListField(
        child=serializers.ImageField(),
        required=False,
        write_only=True,
        max_length=SocialPostMedia.MAX_IMAGES_PER_POST,
    )
    media_order = MultipartJSONField(required=False, write_only=True)
    target_platforms = MultipartListField(
        child=serializers.ChoiceField(
            choices=SOCIAL_PUBLISH_PLATFORM_CHOICES
        ),
        required=False,
        allow_empty=True,
        help_text=(
            "Platforms to publish to. Use an array in JSON, or repeat the "
            "target_platforms form-data key for multipart requests."
        ),
    )
    video = serializers.FileField(required=False, allow_null=True)

    class Meta:
        model = SocialPost
        fields = [
            "id",
            "agency",
            "property",
            "social_account",
            "property_title",
            "platform",
            "target_platforms",
            "post_format",
            "caption",
            "image",
            "video",
            "video_duration_seconds",
            "video_width",
            "video_height",
            "video_size_bytes",
            "media",
            "images",
            "media_order",
            "status",
            "scheduled_at",
            "published_at",
            "error_message",
            "external_post_id",
            "created_by",
            "created_by_name",
            "publish_results",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "agency",
            "created_by",
            "published_at",
            "error_message",
            "external_post_id",
            "video_duration_seconds",
            "video_width",
            "video_height",
            "video_size_bytes",
        ]

    def get_property_title(self, obj) -> str | None:
        return obj.property.title if obj.property else None

    def get_created_by_name(self, obj) -> str | None:
        return obj.created_by.full_name if obj.created_by else None

    def validate_property(self, value):
        request = self.context.get("request")

        if not value:
            return value

        if value.agency != request.user.agency:
            raise serializers.ValidationError(
                "You can only create social posts for your own agency properties."
            )

        return value

    def validate_social_account(self, value):
        if value is None:
            return value
        request = self.context.get("request")
        if value.agency_id != request.user.agency_id:
            raise serializers.ValidationError(
                "You can only use a social account connected to your agency."
            )
        if value.status != value.STATUS_CONNECTED:
            raise serializers.ValidationError("The social account is not connected.")
        return value

    def validate_target_platforms(self, value):
        return list(dict.fromkeys(value))

    def validate_images(self, images):
        for image_file in images:
            if image_file.size > 10 * 1024 * 1024:
                raise serializers.ValidationError(
                    f"{image_file.name} exceeds the 10 MB image limit."
                )

            try:
                image_file.seek(0)
                with Image.open(image_file) as image:
                    width, height = image.size
                    image.verify()
                image_file.seek(0)
            except (UnidentifiedImageError, OSError, ValueError) as exc:
                raise serializers.ValidationError(
                    f"{image_file.name} is not a valid image."
                ) from exc

            if width < 320:
                raise serializers.ValidationError(
                    f"{image_file.name} must be at least 320 pixels wide."
                )
            aspect_ratio = width / height
            if not 0.8 <= aspect_ratio <= 1.91:
                raise serializers.ValidationError(
                    f"{image_file.name} must have an aspect ratio between "
                    "4:5 and 1.91:1."
                )
        return images

    def validate_video(self, video):
        if video is None:
            return video
        try:
            compressed = compress_reel_upload(video)
        except ReelValidationError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        self._compressed_reel = compressed
        return compressed.file

    def _prepare_media_plan(self, attrs):
        existing_items = list(self.instance.media_items.all()) if self.instance else []
        existing_ids = {item.id for item in existing_items}
        has_legacy_image = bool(
            self.instance and self.instance.image and not existing_items
        )
        images = list(attrs.get("images", []))
        legacy_image_supplied = "image" in attrs

        if legacy_image_supplied:
            legacy_image = attrs.get("image")
            images = [legacy_image] if legacy_image else []
            attrs["images"] = images

        if "media_order" in attrs:
            order = attrs["media_order"]
            if not isinstance(order, list):
                raise serializers.ValidationError(
                    {"media_order": "Media order must be a JSON array."}
                )
        elif legacy_image_supplied:
            order = ["new:0"] if images else []
        else:
            order = [f"existing:{item.id}" for item in existing_items]
            if has_legacy_image:
                order.append("legacy:0")
            order.extend(f"new:{index}" for index in range(len(images)))

        if len(order) > SocialPostMedia.MAX_IMAGES_PER_POST:
            raise serializers.ValidationError(
                {
                    "images": (
                        "A social post can contain at most "
                        f"{SocialPostMedia.MAX_IMAGES_PER_POST} images."
                    )
                }
            )

        normalized_order = []
        seen_tokens = set()
        referenced_new_indexes = set()
        for token in order:
            if not isinstance(token, str) or ":" not in token:
                raise serializers.ValidationError(
                    {"media_order": "Each media-order item must be a media token."}
                )
            kind, raw_identifier = token.split(":", 1)
            try:
                identifier = int(raw_identifier)
            except (TypeError, ValueError) as exc:
                raise serializers.ValidationError(
                    {"media_order": f"Invalid media token: {token}."}
                ) from exc

            normalized_token = f"{kind}:{identifier}"
            if normalized_token in seen_tokens:
                raise serializers.ValidationError(
                    {"media_order": "The same image cannot appear more than once."}
                )
            seen_tokens.add(normalized_token)

            if kind == "existing":
                if identifier not in existing_ids:
                    raise serializers.ValidationError(
                        {"media_order": "An existing image does not belong to this post."}
                    )
            elif kind == "legacy":
                if identifier != 0 or not has_legacy_image:
                    raise serializers.ValidationError(
                        {"media_order": "This post does not have a legacy cover image."}
                    )
            elif kind == "new":
                if identifier < 0 or identifier >= len(images):
                    raise serializers.ValidationError(
                        {"media_order": f"Invalid new-image token: {token}."}
                    )
                referenced_new_indexes.add(identifier)
            else:
                raise serializers.ValidationError(
                    {"media_order": f"Unsupported media token: {token}."}
                )
            normalized_order.append((kind, identifier))

        if referenced_new_indexes != set(range(len(images))):
            raise serializers.ValidationError(
                {"media_order": "Every uploaded image must appear in the media order."}
            )

        current_order = [("existing", item.id) for item in existing_items]
        if has_legacy_image:
            current_order.append(("legacy", 0))
        self.media_changed = (
            legacy_image_supplied
            or bool(images)
            or normalized_order != current_order
        )
        self._media_plan = normalized_order

    def _apply_media_plan(self, post, images):
        existing_items = {item.id: item for item in post.media_items.all()}
        retained_ids = {
            identifier
            for kind, identifier in self._media_plan
            if kind == "existing"
        }
        removed_items = [
            item for item_id, item in existing_items.items() if item_id not in retained_ids
        ]
        removed_names = {item.image.name for item in removed_items if item.image.name}

        if removed_items:
            SocialPostMedia.objects.filter(
                id__in=[item.id for item in removed_items]
            ).delete()

        ordered_items = []
        for position, (kind, identifier) in enumerate(self._media_plan):
            if kind == "existing":
                item = existing_items[identifier]
                if item.position != position:
                    item.position = position
                    item.save(update_fields=["position"])
            elif kind == "legacy":
                item = SocialPostMedia.objects.create(
                    post=post,
                    image=post.image.name,
                    position=position,
                )
            else:
                item = SocialPostMedia.objects.create(
                    post=post,
                    image=images[identifier],
                    position=position,
                )
            ordered_items.append(item)

        first_item = ordered_items[0] if ordered_items else None
        post.image.name = first_item.image.name if first_item else None
        post.save(update_fields=["image", "updated_at"])

        retained_names = {item.image.name for item in ordered_items if item.image.name}
        for removed_item in removed_items:
            name = removed_item.image.name
            if name and name in removed_names - retained_names:
                storage = removed_item.image.storage
                transaction.on_commit(lambda name=name, storage=storage: storage.delete(name))

    def validate(self, attrs):
        self._compressed_reel = getattr(self, "_compressed_reel", None)
        self.media_changed = False
        self._prepare_media_plan(attrs)
        post_format = attrs.get(
            "post_format",
            self.instance.post_format if self.instance else SocialPost.FORMAT_IMAGE,
        )
        if self.instance and post_format != self.instance.post_format:
            raise serializers.ValidationError(
                {"post_format": "Create a new post to change between an image post and a Reel."}
            )
        if post_format == SocialPost.FORMAT_REEL:
            if self._media_plan:
                raise serializers.ValidationError(
                    {"images": "A Reel accepts one video and cannot contain images."}
                )
            reel_video = attrs.get(
                "video",
                self.instance.video if self.instance else None,
            )
            if not reel_video:
                raise serializers.ValidationError(
                    {"video": "Upload a video for the Reel."}
                )
        elif "video" in attrs and attrs.get("video"):
            raise serializers.ValidationError(
                {"video": "Select the Reel format before uploading a video."}
            )

        self.media_changed = self.media_changed or "video" in attrs
        status_value = attrs.get(
            "status",
            self.instance.status if self.instance else SocialPost.STATUS_DRAFT,
        )
        scheduled_at = attrs.get(
            "scheduled_at",
            self.instance.scheduled_at if self.instance else None,
        )
        social_account = attrs.get(
            "social_account",
            self.instance.social_account if self.instance else None,
        )

        if status_value == SocialPost.STATUS_SCHEDULED:
            if scheduled_at is None:
                raise serializers.ValidationError(
                    {"scheduled_at": "Scheduled time is required."}
                )
            if social_account is None:
                raise serializers.ValidationError(
                    {"social_account": "A connected account is required."}
                )
            if scheduled_at <= timezone.now():
                raise serializers.ValidationError(
                    {"scheduled_at": "Scheduled time must be in the future."}
                )
            target_platforms = attrs.get(
                "target_platforms",
                self.instance.target_platforms if self.instance else [],
            ) or [attrs.get("platform", self.instance.platform if self.instance else None)]
            for target_platform in target_platforms:
                if target_platform == social_account.platform:
                    continue
                counterpart_exists = SocialAccount.objects.filter(
                    agency=social_account.agency,
                    provider=SocialAccount.PROVIDER_META,
                    platform=target_platform,
                    page_id=social_account.page_id,
                    status=SocialAccount.STATUS_CONNECTED,
                ).exists()
                if not counterpart_exists:
                    raise serializers.ValidationError(
                        {
                            "target_platforms": (
                                f"No connected {target_platform} account is linked "
                                "to the selected Page."
                            )
                        }
                    )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        images = validated_data.pop("images", [])
        validated_data.pop("media_order", None)
        validated_data.pop("image", None)
        if self._compressed_reel:
            validated_data.update(
                {
                    "video_duration_seconds": self._compressed_reel.duration_seconds,
                    "video_width": self._compressed_reel.width,
                    "video_height": self._compressed_reel.height,
                    "video_size_bytes": self._compressed_reel.size_bytes,
                }
            )
        post = super().create(validated_data)
        self._apply_media_plan(post, images)
        return post

    @transaction.atomic
    def update(self, instance, validated_data):
        images = validated_data.pop("images", [])
        validated_data.pop("media_order", None)
        validated_data.pop("image", None)
        old_video_name = instance.video.name if instance.video else ""
        old_video_storage = instance.video.storage if instance.video else None
        if self._compressed_reel:
            validated_data.update(
                {
                    "video_duration_seconds": self._compressed_reel.duration_seconds,
                    "video_width": self._compressed_reel.width,
                    "video_height": self._compressed_reel.height,
                    "video_size_bytes": self._compressed_reel.size_bytes,
                }
            )
        post = super().update(instance, validated_data)
        if self.media_changed:
            self._apply_media_plan(post, images)
        if (
            self._compressed_reel
            and old_video_name
            and old_video_name != post.video.name
            and old_video_storage
        ):
            transaction.on_commit(
                lambda: old_video_storage.delete(old_video_name)
            )
        return post


class SocialPublishRequestSerializer(serializers.Serializer):
    platforms = serializers.ListField(
        child=serializers.ChoiceField(
            choices=SOCIAL_PUBLISH_PLATFORM_CHOICES
        ),
        required=False,
        allow_empty=False,
    )

    def validate_platforms(self, value):
        return list(dict.fromkeys(value))


class MetaPageSelectionSerializer(serializers.Serializer):
    page_ids = serializers.ListField(
        child=serializers.CharField(max_length=255),
        allow_empty=False,
        max_length=25,
    )

    def validate_page_ids(self, value):
        return list(dict.fromkeys(value))


class SocialConnectionSessionSerializer(serializers.ModelSerializer):
    pages = serializers.SerializerMethodField()

    class Meta:
        model = SocialConnectionSession
        fields = ["token", "provider", "pages", "expires_at"]

    def get_pages(self, obj):
        return [
            {
                "id": str(page.get("id", "")),
                "name": page.get("name") or "Unnamed Page",
                "has_instagram": bool(page.get("instagram_business_account")),
                "instagram_username": (
                    (page.get("instagram_business_account") or {}).get("username")
                ),
            }
            for page in obj.candidate_pages
            if page.get("id")
        ]


class SocialAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = SocialAccount
        fields = [
            "id",
            "provider",
            "platform",
            "external_id",
            "name",
            "username",
            "page_id",
            "status",
            "webhook_subscription_status",
            "webhook_subscribed_at",
            "webhook_error",
            "created_at",
            "updated_at",
        ]
