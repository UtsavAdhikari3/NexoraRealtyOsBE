from django.conf import settings
from django.db import transaction
from django.utils import timezone
from datetime import timedelta

from rest_framework import serializers
from PIL import Image, UnidentifiedImageError

from .models import (
    Property, PropertyMedia, PropertyVerification, PropertyVerificationDocument,
    PropertyHistory, PropertyDuplicateFlag,
    PropertyDistributionLink,
)
from .area import conversion_payload, price_per_area
from .media_renditions import delete_unreferenced_files, generate_property_media_renditions, media_files


class PropertyDistributionSocialDraftRequestSerializer(serializers.Serializer):
    """Validate the generated social-draft handoff from property distribution."""

    social_account = serializers.IntegerField(min_value=1)
    language = serializers.ChoiceField(
        choices=["english", "nepali"],
        default="english",
    )
    link = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    asset_type = serializers.ChoiceField(
        choices=["facebook_post", "instagram_post"],
        required=False,
    )
    publish_now = serializers.BooleanField(
        required=False,
        default=False,
        help_text=(
            "Deprecated compatibility field. This endpoint always creates a draft; "
            "publish it through /api/social-posts/posts/{id}/publish/."
        ),
    )


class PropertyMediaSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyMedia
        fields = [
            "id",
            "property",
            "media_type",
            "file",
            "external_url",
            "thumbnail",
            "card_image",
            "large_image",
            "original_width",
            "original_height",
            "card_width",
            "card_height",
            "large_width",
            "large_height",
            "title",
            "caption",
            "alt_text",
            "is_public",
            "sort_order",
            "is_primary",
            "uploaded_by",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "property",
            "uploaded_by",
            "card_image",
            "large_image",
            "original_width",
            "original_height",
            "card_width",
            "card_height",
            "large_width",
            "large_height",
            "created_at",
        ]

    def validate_file(self, value):
        if value is None:
            return value

        max_size_mb = getattr(settings, "MAX_UPLOAD_SIZE_MB", 15)
        if value.size > max_size_mb * 1024 * 1024:
            raise serializers.ValidationError(
                f"File size cannot exceed {max_size_mb} MB."
            )

        allowed_types = getattr(
            settings,
            "ALLOWED_MEDIA_CONTENT_TYPES",
            [
                "image/jpeg",
                "image/png",
                "image/webp",
                "application/pdf",
                "video/mp4",
            ],
        )
        content_type = getattr(value, "content_type", "")
        if content_type and content_type not in allowed_types:
            raise serializers.ValidationError("Unsupported file type.")
        return value

    def validate(self, attrs):
        file_value = attrs.get("file", getattr(self.instance, "file", None))
        external_url = attrs.get(
            "external_url",
            getattr(self.instance, "external_url", ""),
        )
        if not file_value and not external_url:
            raise serializers.ValidationError(
                "Provide either an uploaded file or an external URL."
            )
        media_type = attrs.get("media_type", getattr(self.instance, "media_type", "image"))
        if file_value and media_type == "image":
            try:
                file_value.seek(0)
                with Image.open(file_value) as image:
                    image.verify()
                file_value.seek(0)
                with Image.open(file_value) as image:
                    width, height = image.size
                    if image.format not in {"JPEG", "PNG", "WEBP"}:
                        raise serializers.ValidationError({"file": "Use a JPEG, PNG, or WebP image."})
                    if width > 12000 or height > 12000 or width * height > 50_000_000:
                        raise serializers.ValidationError({"file": "Image dimensions are too large."})
                    expected_content_types = {
                        "JPEG": {"image/jpeg", "image/pjpeg"},
                        "PNG": {"image/png"},
                        "WEBP": {"image/webp"},
                    }
                    content_type = getattr(file_value, "content_type", "")
                    if content_type and content_type not in expected_content_types[image.format]:
                        raise serializers.ValidationError({"file": "The file content does not match its MIME type."})
            except (UnidentifiedImageError, OSError, ValueError):
                raise serializers.ValidationError({"file": "Upload a valid, non-corrupt image."})
            finally:
                file_value.seek(0)
        return attrs

    def create(self, validated_data):
        with transaction.atomic():
            if validated_data.get("is_primary"):
                PropertyMedia.objects.filter(
                    property=validated_data["property"],
                    is_primary=True,
                ).update(is_primary=False)
            instance = super().create(validated_data)
            if instance.media_type == "image" and instance.file:
                generate_property_media_renditions(instance)
        return instance

    def update(self, instance, validated_data):
        old_files = media_files(instance)
        should_regenerate = "file" in validated_data or "media_type" in validated_data
        with transaction.atomic():
            if validated_data.get("is_primary", instance.is_primary):
                PropertyMedia.objects.filter(
                    property=instance.property,
                    is_primary=True,
                ).exclude(id=instance.id).update(is_primary=False)
            instance = super().update(instance, validated_data)
            if should_regenerate:
                generate_property_media_renditions(instance)
        delete_unreferenced_files(old_files, exclude_pk=instance.pk)
        return instance


class PropertyVerificationDocumentSerializer(serializers.ModelSerializer):
    document_type_display = serializers.CharField(source="get_document_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    reviewed_by_name = serializers.CharField(source="reviewed_by.full_name", read_only=True, allow_null=True)

    class Meta:
        model = PropertyVerificationDocument
        fields = [
            "id", "document_type", "document_type_display", "status", "status_display",
            "file", "external_url", "document_number", "issued_date", "expiry_date",
            "notes", "reviewed_by", "reviewed_by_name", "reviewed_at", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "document_type", "reviewed_by", "reviewed_by_name", "reviewed_at",
            "created_at", "updated_at",
        ]

    def validate_file(self, value):
        if value is None:
            return value
        max_size_mb = getattr(settings, "MAX_UPLOAD_SIZE_MB", 15)
        if value.size > max_size_mb * 1024 * 1024:
            raise serializers.ValidationError(f"File size cannot exceed {max_size_mb} MB.")
        allowed = {
            "image/jpeg", "image/png", "image/webp", "application/pdf",
        }
        content_type = getattr(value, "content_type", "")
        if content_type and content_type not in allowed:
            raise serializers.ValidationError("Upload a PDF, JPEG, PNG, or WebP document.")
        return value

    def validate(self, attrs):
        issued = attrs.get("issued_date", getattr(self.instance, "issued_date", None))
        expiry = attrs.get("expiry_date", getattr(self.instance, "expiry_date", None))
        if issued and expiry and expiry < issued:
            raise serializers.ValidationError({"expiry_date": "Expiry date cannot be before issued date."})
        status_value = attrs.get("status", getattr(self.instance, "status", "missing"))
        file_value = attrs.get("file", getattr(self.instance, "file", None))
        external_url = attrs.get(
            "external_url", getattr(self.instance, "external_url", "")
        )
        if status_value in {"received", "under_review", "approved", "rejected"} and not (
            file_value or external_url
        ):
            raise serializers.ValidationError({
                "status": "Upload a document or provide its URL before changing this status."
            })
        return attrs

    def update(self, instance, validated_data):
        new_file = validated_data.get("file")
        new_url = validated_data.get("external_url")
        if instance.status == "missing" and (new_file or new_url) and "status" not in validated_data:
            validated_data["status"] = "received"
        if validated_data.get("status") in {"approved", "rejected", "not_applicable"}:
            request = self.context.get("request")
            validated_data["reviewed_by"] = request.user if request else None
            validated_data["reviewed_at"] = timezone.now()
        elif "status" in validated_data:
            validated_data["reviewed_by"] = None
            validated_data["reviewed_at"] = None
        return super().update(instance, validated_data)


class PropertyVerificationSerializer(serializers.ModelSerializer):
    documents = PropertyVerificationDocumentSerializer(many=True, read_only=True)
    verification_level = serializers.CharField(read_only=True)
    verification_level_display = serializers.CharField(read_only=True)
    completed_milestones = serializers.SerializerMethodField()
    approved_document_count = serializers.SerializerMethodField()
    total_document_count = serializers.SerializerMethodField()
    updated_by_name = serializers.CharField(source="updated_by.full_name", read_only=True, allow_null=True)

    class Meta:
        model = PropertyVerification
        fields = [
            "id", "verification_level", "verification_level_display",
            "owner_identity_verified", "owner_identity_verified_at",
            "ownership_document_received", "ownership_document_received_at",
            "physically_inspected", "physically_inspected_at",
            "documents_reviewed", "documents_reviewed_at",
            "fully_verified", "fully_verified_at", "inspection_notes", "review_notes",
            "completed_milestones", "approved_document_count", "total_document_count",
            "updated_by", "updated_by_name", "documents", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "owner_identity_verified_at", "ownership_document_received_at",
            "physically_inspected_at", "documents_reviewed_at", "fully_verified_at",
            "updated_by", "created_at", "updated_at",
        ]

    def get_completed_milestones(self, obj):
        return sum(bool(getattr(obj, field)) for field, _ in obj.MILESTONES)

    def get_approved_document_count(self, obj):
        return obj.documents.filter(status__in=["approved", "not_applicable"]).count()

    def get_total_document_count(self, obj):
        return len(PropertyVerificationDocument.DOCUMENT_TYPES)

    def validate(self, attrs):
        values = {
            field: attrs.get(field, getattr(self.instance, field, False))
            for field, _ in PropertyVerification.MILESTONES
        }
        seen_false = False
        for field, _ in PropertyVerification.MILESTONES:
            if seen_false and values[field]:
                raise serializers.ValidationError({field: "Complete the previous verification milestones first."})
            seen_false = seen_false or not values[field]

        documents = self.instance.documents.all() if self.instance else []
        status_by_type = {document.document_type: document.status for document in documents}
        if values["ownership_document_received"] and status_by_type.get("lalpurja") == "missing":
            raise serializers.ValidationError({
                "ownership_document_received": "Mark the Lalpurja as received before completing this milestone."
            })
        if values["documents_reviewed"]:
            unresolved = [status for status in status_by_type.values() if status not in {"approved", "rejected", "not_applicable"}]
            if unresolved:
                raise serializers.ValidationError({"documents_reviewed": "Resolve every checklist document first."})
        if values["fully_verified"]:
            incomplete = [status for status in status_by_type.values() if status not in {"approved", "not_applicable"}]
            if incomplete:
                raise serializers.ValidationError({"fully_verified": "Every applicable document must be approved."})
        return attrs

    def update(self, instance, validated_data):
        for field, _ in PropertyVerification.MILESTONES:
            if field in validated_data and validated_data[field] != getattr(instance, field):
                validated_data[f"{field}_at"] = timezone.now() if validated_data[field] else None
        request = self.context.get("request")
        validated_data["updated_by"] = request.user if request else None
        return super().update(instance, validated_data)


class PropertyHistorySerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.full_name", read_only=True, allow_null=True)
    event_type_display = serializers.CharField(source="get_event_type_display", read_only=True)

    class Meta:
        model = PropertyHistory
        fields = ["id", "event_type", "event_type_display", "summary", "changes", "note", "actor_name", "created_at"]
        read_only_fields = fields


class PropertyDuplicateFlagSerializer(serializers.ModelSerializer):
    candidate_title = serializers.CharField(source="candidate.title", read_only=True)
    candidate_display_id = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    reviewed_by_name = serializers.CharField(source="reviewed_by.full_name", read_only=True, allow_null=True)

    class Meta:
        model = PropertyDuplicateFlag
        fields = [
            "id", "candidate", "candidate_title", "candidate_display_id", "score", "reasons",
            "status", "status_display", "reviewed_by_name", "reviewed_at", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "candidate", "candidate_title", "candidate_display_id", "score", "reasons",
            "reviewed_by_name", "reviewed_at", "created_at", "updated_at",
        ]

    def get_candidate_display_id(self, obj):
        return f"LP-{obj.candidate_id:03d}"


class PropertyDistributionLinkSerializer(serializers.ModelSerializer):
    short_url = serializers.SerializerMethodField()

    class Meta:
        model = PropertyDistributionLink
        fields = [
            "id", "code", "label", "source", "medium", "campaign",
            "short_url", "is_active", "click_count", "last_clicked_at",
            "created_by", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "code", "short_url", "click_count", "last_clicked_at",
            "created_by", "created_at", "updated_at",
        ]

    def get_short_url(self, obj):
        from .distribution import tracked_url
        return tracked_url(obj, self.context.get("request"))

    def validate_source(self, value):
        cleaned = value.strip().lower().replace(" ", "_")
        if not cleaned:
            raise serializers.ValidationError("Source is required.")
        return cleaned

class PropertySerializer(serializers.ModelSerializer):
    media = PropertyMediaSerializer(many=True, read_only=True)

    assigned_agent_name = serializers.SerializerMethodField()
    assigned_agent_detail = serializers.SerializerMethodField()

    display_property_id = serializers.SerializerMethodField()
    price_per_sqft = serializers.SerializerMethodField()
    land_area_conversions = serializers.SerializerMethodField()
    price_per_aana = serializers.SerializerMethodField()
    price_per_dhur = serializers.SerializerMethodField()
    price_per_kattha = serializers.SerializerMethodField()
    price_per_land_sqft = serializers.SerializerMethodField()
    furnishing_status_display = serializers.SerializerMethodField()
    facing_direction_display = serializers.SerializerMethodField()
    verification = PropertyVerificationSerializer(read_only=True, allow_null=True)
    freshness_state = serializers.SerializerMethodField()
    days_until_expiry = serializers.SerializerMethodField()
    pending_duplicate_count = serializers.SerializerMethodField()

    class Meta:
        model = Property
        fields = "__all__"
        read_only_fields = (
            "agency",
            "share_slug",
            "availability_verified_at", "listing_expires_at", "owner_confirmed_at",
            "withdrawn_at", "requires_republish_approval", "republish_approval_status",
            "republish_requested_at", "republish_requested_by", "republish_approved_at",
            "republish_approved_by", "republish_rejection_reason",
        )

    def get_freshness_state(self, obj):
        if not obj.availability_verified_at or not obj.listing_expires_at:
            return "unconfirmed"
        if obj.listing_expires_at <= timezone.now():
            return "expired"
        if obj.listing_expires_at <= timezone.now() + timedelta(days=7):
            return "expiring_soon"
        return "fresh"

    def get_days_until_expiry(self, obj):
        if not obj.listing_expires_at:
            return None
        return max(0, (obj.listing_expires_at - timezone.now()).days)

    def get_pending_duplicate_count(self, obj):
        return sum(flag.status == "pending" for flag in obj.duplicate_flags.all())

    def get_assigned_agent_name(self, obj) -> str | None:
        if obj.assigned_agent:
            return obj.assigned_agent.full_name

        return None

    def get_assigned_agent_detail(self, obj) -> dict | None:
        if not obj.assigned_agent:
            return None

        return {
            "id": obj.assigned_agent.id,
            "full_name": obj.assigned_agent.full_name,
            "email": obj.assigned_agent.email,
            "role": obj.assigned_agent.role,
        }

    def get_display_property_id(self, obj) -> str:
        return f"LP-{obj.id:03d}"

    def get_price_per_sqft(self, obj) -> str | None:
        return price_per_area(obj.price, obj.built_up_area_value, obj.built_up_area_unit, "sqft")

    def get_land_area_conversions(self, obj):
        return conversion_payload(obj.land_area_value, obj.land_area_unit)

    def get_price_per_aana(self, obj): return price_per_area(obj.price, obj.land_area_value, obj.land_area_unit, "aana")
    def get_price_per_dhur(self, obj): return price_per_area(obj.price, obj.land_area_value, obj.land_area_unit, "dhur")
    def get_price_per_kattha(self, obj): return price_per_area(obj.price, obj.land_area_value, obj.land_area_unit, "kattha")
    def get_price_per_land_sqft(self, obj): return price_per_area(obj.price, obj.land_area_value, obj.land_area_unit, "sqft")

    def get_furnishing_status_display(self, obj) -> str | None:
        if not obj.furnishing_status:
            return None

        return obj.get_furnishing_status_display()

    def get_facing_direction_display(self, obj) -> str | None:
        if not obj.facing_direction:
            return None

        return obj.get_facing_direction_display()

    def validate_assigned_agent(self, value):
        request = self.context["request"]

        if value is None:
            return value

        if value.agency != request.user.agency:
            raise serializers.ValidationError(
                "Assigned agent must belong to your agency."
            )

        if value.role != "agent":
            raise serializers.ValidationError(
                "Assigned user must be an agent."
            )

        return value

    def validate(self, attrs):
        def current(name, default=None):
            return attrs.get(name, getattr(self.instance, name, default) if self.instance else default)

        for value_field, unit_field in (
            ("land_area_value", "land_area_unit"), ("built_up_area_value", "built_up_area_unit"),
            ("road_access_value", "road_access_unit"),
            ("major_road_distance_value", "major_road_distance_unit"),
        ):
            value, unit = current(value_field), current(unit_field)
            if value is not None and value <= 0:
                raise serializers.ValidationError({value_field: "Must be greater than zero."})
            if value is not None and not unit:
                raise serializers.ValidationError({unit_field: "Select a unit."})
        for field in ("mohada_value", "pichhad_value"):
            if current(field) is not None and current(field) <= 0:
                raise serializers.ValidationError({field: "Must be greater than zero."})
        ward = str(current("ward_number", "")).strip()
        if ward and (not ward.isdigit() or int(ward) < 1 or int(ward) > 99):
            raise serializers.ValidationError({"ward_number": "Enter a ward number from 1 to 99."})

        purpose = current("purpose")
        rent_period = current("rent_period")
        if purpose in {"rent", "lease"} and not rent_period:
            raise serializers.ValidationError({"rent_period": "Select whether this price is weekly, monthly, or yearly."})
        if purpose == "sale":
            attrs["rent_period"] = None

        status_value = attrs.get(
            "status",
            self.instance.status if self.instance else "draft",
        )
        is_published = attrs.get(
            "is_published",
            self.instance.is_published if self.instance else False,
        )
        if "is_published" not in attrs and status_value not in {"available", "reserved", "under_negotiation"}:
            is_published = False

        if is_published and status_value not in {"available", "reserved", "under_negotiation"}:
            raise serializers.ValidationError(
                {
                    "is_published": (
                        "Only available, reserved, or under-negotiation properties can be published."
                    )
                }
            )

        if is_published and self.instance:
            if self.instance.requires_republish_approval:
                raise serializers.ValidationError({
                    "is_published": "Manager approval is required before this listing can be republished."
                })
            if self.instance.listing_expires_at and self.instance.listing_expires_at <= timezone.now():
                raise serializers.ValidationError({
                    "is_published": "Confirm listing availability before republishing an expired listing."
                })

        withdrawal_reason = attrs.get(
            "withdrawal_reason", getattr(self.instance, "withdrawal_reason", "") if self.instance else ""
        )
        if status_value == "withdrawn" and not str(withdrawal_reason).strip():
            raise serializers.ValidationError({"withdrawal_reason": "Provide a reason for withdrawal."})

        request = self.context.get("request")
        if request and request.user.agency_id:
            from operations.validators import validate_custom_data
            validate_custom_data(
                request.user.agency,
                "property",
                attrs.get("custom_data", getattr(self.instance, "custom_data", {})),
            )

        return attrs
