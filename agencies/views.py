from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import Http404
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone
from pathlib import Path
from uuid import uuid4
from copy import deepcopy

from PIL import Image

from rest_framework import status
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .serializers import TestMarkAgencyPaidSerializer
from .serializers import AgencySerializer, WebsiteOnboardingSerializer
from .models import Agency
from .website_onboarding import (
    MEDIA_KEYS,
    materialize_website_config,
    website_readiness,
)
from drf_spectacular.utils import extend_schema, inline_serializer

User = get_user_model()


class LocalizationView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses=inline_serializer(
            name="AgencyLocalizationSettings",
            fields={
                "language": serializers.ChoiceField(choices=["en", "ne"]),
                "date_system": serializers.ChoiceField(choices=["ad", "bs"]),
                "use_nepali_digits": serializers.BooleanField(),
                "timezone": serializers.CharField(),
                "now": serializers.JSONField(),
                "message_templates": serializers.JSONField(),
            },
        )
    )
    def get(self, request):
        from django.utils import timezone
        from .localization import (
            format_localized_date, resolved_message_templates,
        )

        agency = request.user.agency
        if not agency:
            return Response(
                {"detail": "An agency account is required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        now = timezone.now()
        return Response({
            "language": agency.default_language,
            "date_system": agency.default_date_system,
            "use_nepali_digits": agency.use_nepali_digits,
            "timezone": agency.timezone,
            "now": {
                "iso": now.isoformat(),
                "ad": format_localized_date(
                    now, date_system="ad", language=agency.default_language,
                    nepali_digits=agency.use_nepali_digits, include_time=True,
                ),
                "bs": format_localized_date(
                    now, date_system="bs", language=agency.default_language,
                    nepali_digits=agency.use_nepali_digits, include_time=True,
                ),
            },
            "message_templates": resolved_message_templates(agency.message_templates),
        })

    @extend_schema(
        request=inline_serializer(
            name="AgencyDateConversionRequest",
            fields={
                "date": serializers.CharField(),
                "source": serializers.ChoiceField(choices=["ad", "bs"]),
                "target": serializers.ChoiceField(choices=["ad", "bs"]),
                "language": serializers.ChoiceField(choices=["en", "ne"], required=False),
                "use_nepali_digits": serializers.BooleanField(required=False),
            },
        ),
        responses=inline_serializer(
            name="AgencyDateConversionResponse",
            fields={
                "source": serializers.CharField(),
                "target": serializers.CharField(),
                "date": serializers.CharField(),
                "display": serializers.CharField(),
            },
        ),
    )
    def post(self, request):
        from .localization import convert_date, format_localized_date

        value = request.data.get("date")
        source = request.data.get("source", "ad")
        target = request.data.get("target", "bs")
        if not value or source not in {"ad", "bs"} or target not in {"ad", "bs"} or source == target:
            return Response(
                {"detail": "Provide a date and different ad/bs source and target systems."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            nepali_digits = request.data.get("use_nepali_digits", False)
            if isinstance(nepali_digits, str):
                nepali_digits = nepali_digits.strip().lower() in {"1", "true", "yes", "on"}
            converted = convert_date(value, target=target)
            iso = f"{converted['year']:04d}-{converted['month']:02d}-{converted['day']:02d}"
            if target == "bs":
                display = format_localized_date(
                    value, date_system="bs",
                    language=request.data.get("language", "en"),
                    nepali_digits=bool(nepali_digits),
                )
            else:
                display = format_localized_date(
                    iso, date_system="ad",
                    language=request.data.get("language", "en"),
                    nepali_digits=bool(nepali_digits),
                )
        except (ValueError, TypeError, OverflowError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"source": source, "target": target, "date": iso, "display": display})


class CurrentAgencyView(APIView):
    serializer_class = AgencySerializer

    def get(self, request):
        if not request.user.is_authenticated or not request.user.agency_id:
            return Response(
                {"detail": "An agency account is required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(
            self.serializer_class(
                request.user.agency,
                context={"request": request},
            ).data
        )

    def patch(self, request):
        if not request.user.is_authenticated or not request.user.agency_id:
            return Response(
                {"detail": "An agency account is required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if request.user.role not in ["agency_owner", "agency_manager"]:
            return Response(
                {"detail": "Only owners or managers can update agency settings."},
                status=status.HTTP_403_FORBIDDEN,
            )
        was_completed = request.user.agency.website_onboarding_status == Agency.WEBSITE_ONBOARDING_COMPLETED
        serializer = self.serializer_class(
            request.user.agency,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        incoming = deepcopy(serializer.validated_data.get("website_config") or instance.website_draft_config or {})
        field_map = {
            "about": "about", "email": "public_email", "phone": "public_phone", "address": "address",
            "business_hours": "business_hours", "primary_color": "primary_color", "seo_title": "seo_title",
            "seo_description": "seo_description", "facebook_url": "facebook_url", "instagram_url": "instagram_url",
            "linkedin_url": "linkedin_url", "youtube_url": "youtube_url", "tiktok_url": "tiktok_url",
            "whatsapp_number": "whatsapp_number", "viber_number": "viber_number", "default_language": "language",
        }
        for agency_field, config_field in field_map.items():
            if agency_field in serializer.validated_data:
                incoming[config_field] = serializer.validated_data[agency_field] or ""
        media = dict(incoming.get("media") or {})
        if "logo" in serializer.validated_data and instance.logo:
            media["logo"] = instance.logo.name
        if "cover_image" in serializer.validated_data and instance.cover_image:
            media["hero_image"] = instance.cover_image.name
        incoming["media"] = media
        instance.website_draft_config = materialize_website_config(instance, incoming)
        readiness = website_readiness(instance, instance.website_draft_config)
        instance.website_completion_percentage = readiness["completion_percentage"]
        instance.website_onboarding_status = Agency.WEBSITE_ONBOARDING_COMPLETED if was_completed else (
            Agency.WEBSITE_ONBOARDING_READY if readiness["is_ready_to_publish"] else Agency.WEBSITE_ONBOARDING_IN_PROGRESS
        )
        instance.save(update_fields=[
            "website_draft_config", "website_completion_percentage", "website_onboarding_status",
        ])
        return Response(self.serializer_class(instance, context={"request": request}).data)


class WebsiteOnboardingView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = WebsiteOnboardingSerializer

    def get_agency(self, request):
        agency = getattr(request.user, "agency", None)
        if not agency:
            return None, Response(
                {"detail": "An agency account is required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if request.user.role not in ["agency_owner", "agency_manager"]:
            return None, Response(
                {"detail": "Only owners or managers can configure the agency website."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return agency, None

    def get(self, request):
        agency, error = self.get_agency(request)
        if error:
            return error
        return Response(self.serializer_class(agency, context={"request": request}).data)

    def patch(self, request):
        agency, error = self.get_agency(request)
        if error:
            return error
        serializer = self.serializer_class(
            agency,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return Response(self.serializer_class(instance, context={"request": request}).data)


class WebsiteValidateView(WebsiteOnboardingView):
    def post(self, request):
        agency, error = self.get_agency(request)
        if error:
            return error
        return Response(website_readiness(agency))


class WebsiteCompleteView(WebsiteOnboardingView):
    def post(self, request):
        agency, error = self.get_agency(request)
        if error:
            return error
        readiness = website_readiness(agency)
        if not readiness["is_ready_to_publish"]:
            return Response(readiness, status=status.HTTP_400_BAD_REQUEST)
        agency.website_onboarding_status = Agency.WEBSITE_ONBOARDING_READY
        agency.website_onboarding_completed_at = timezone.now()
        agency.website_completion_percentage = 100
        agency.save(update_fields=[
            "website_onboarding_status", "website_onboarding_completed_at", "website_completion_percentage",
        ])
        return Response(self.serializer_class(agency, context={"request": request}).data)


class WebsitePreviewView(WebsiteOnboardingView):
    def get(self, request):
        agency, error = self.get_agency(request)
        if error:
            return error
        data = self.serializer_class(agency, context={"request": request}).data
        return Response({"preview_url": data["preview_url"], "expires_in": 86400, "config_version": agency.website_config_version})


class WebsiteMediaView(WebsiteOnboardingView):
    allowed_types = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/x-icon": ".ico"}

    def post(self, request):
        agency, error = self.get_agency(request)
        if error:
            return error
        kind = str(request.data.get("kind", "")).strip()
        upload = request.FILES.get("file")
        if kind not in MEDIA_KEYS:
            return Response({"kind": ["Choose a supported website media type."]}, status=status.HTTP_400_BAD_REQUEST)
        if not upload:
            return Response({"file": ["Select an image to upload."]}, status=status.HTTP_400_BAD_REQUEST)
        if upload.size > 5 * 1024 * 1024:
            return Response({"file": ["Images must be 5 MB or smaller."]}, status=status.HTTP_400_BAD_REQUEST)
        content_type = getattr(upload, "content_type", "")
        if content_type not in self.allowed_types:
            return Response({"file": ["Upload a JPG, PNG, WebP, or ICO image."]}, status=status.HTTP_400_BAD_REQUEST)
        try:
            image = Image.open(upload)
            width, height = image.size
            image.verify()
            upload.seek(0)
        except Exception:
            return Response({"file": ["The uploaded file is not a valid image."]}, status=status.HTTP_400_BAD_REQUEST)
        minimum = (32, 32) if kind == "favicon" else ((800, 400) if kind in {"hero_image", "social_share_image"} else (64, 64))
        if width < minimum[0] or height < minimum[1] or width > 8000 or height > 8000:
            return Response({"file": [f"{kind.replace('_', ' ').title()} must be at least {minimum[0]}×{minimum[1]} and at most 8000×8000 pixels."]}, status=status.HTTP_400_BAD_REQUEST)
        extension = self.allowed_types[content_type]
        path = f"agency_websites/{agency.id}/{kind}/{uuid4().hex}{extension}"
        saved_path = default_storage.save(path, upload)
        config = materialize_website_config(agency)
        previous = config["media"].get(kind)
        if kind == "partner_logos":
            partners = list(previous or [])
            if len(partners) >= 12:
                default_storage.delete(saved_path)
                return Response({"file": ["A maximum of 12 partner logos is allowed."]}, status=status.HTTP_400_BAD_REQUEST)
            config["media"][kind] = [*partners, saved_path]
        else:
            config["media"][kind] = saved_path
        agency.website_draft_config = config
        if agency.website_onboarding_status != Agency.WEBSITE_ONBOARDING_COMPLETED:
            agency.website_onboarding_status = Agency.WEBSITE_ONBOARDING_IN_PROGRESS
        agency.save(update_fields=["website_draft_config", "website_onboarding_status"])
        published_media = (agency.website_published_config.get("media") or {}) if agency.website_published_config else {}
        if kind != "partner_logos" and previous and previous != published_media.get(kind) and previous.startswith(f"agency_websites/{agency.id}/"):
            default_storage.delete(previous)
        return Response(self.serializer_class(agency, context={"request": request}).data, status=status.HTTP_201_CREATED)

    def delete(self, request):
        agency, error = self.get_agency(request)
        if error:
            return error
        kind = str(request.data.get("kind", "")).strip()
        if kind not in MEDIA_KEYS:
            return Response({"kind": ["Choose a supported website media type."]}, status=status.HTTP_400_BAD_REQUEST)
        config = materialize_website_config(agency)
        previous = config["media"].get(kind)
        if kind == "partner_logos":
            target = str(request.data.get("path", ""))
            if target not in (previous or []):
                return Response({"path": ["This partner logo does not belong to the agency draft."]}, status=status.HTTP_404_NOT_FOUND)
            config["media"][kind] = [item for item in previous if item != target]
            previous = target
        else:
            config["media"][kind] = ""
        agency.website_draft_config = config
        if agency.website_onboarding_status != Agency.WEBSITE_ONBOARDING_COMPLETED:
            agency.website_onboarding_status = Agency.WEBSITE_ONBOARDING_IN_PROGRESS
        agency.save(update_fields=["website_draft_config", "website_onboarding_status"])
        published_media = (agency.website_published_config.get("media") or {}) if agency.website_published_config else {}
        published_values = published_media.get(kind, []) if kind == "partner_logos" else [published_media.get(kind)]
        if previous and previous not in published_values and previous.startswith(f"agency_websites/{agency.id}/"):
            default_storage.delete(previous)
        return Response(self.serializer_class(agency, context={"request": request}).data)


class WebsitePublishView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        agency = getattr(request.user, "agency", None)
        if not agency:
            return Response(
                {"detail": "An agency account is required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if request.user.role not in ["agency_owner", "agency_manager"]:
            return Response(
                {"detail": "Only owners or managers can publish the agency website."},
                status=status.HTTP_403_FORBIDDEN,
            )
        agency = Agency.objects.select_for_update().get(pk=agency.pk)
        if not agency.has_active_subscription:
            return Response(
                {"detail": "An active Nexora subscription is required before publishing."},
                status=status.HTTP_403_FORBIDDEN,
            )

        readiness = website_readiness(agency)
        if not readiness["is_ready_to_publish"]:
            return Response(
                {
                    "detail": "Complete the required website information before publishing.",
                    **readiness,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        now = timezone.now()
        published = materialize_website_config(agency)
        agency.website_published_config = published
        agency.website_config = published  # Legacy readers remain compatible during rollout.
        agency.website_draft_config = deepcopy(published)
        agency.website_draft_config["accuracy_confirmed"] = False
        agency.website_onboarding_status = Agency.WEBSITE_ONBOARDING_COMPLETED
        agency.website_onboarding_completed_at = now
        agency.website_published_at = now
        agency.is_website_published = True
        agency.website_completion_percentage = 100
        agency.website_config_version += 1
        agency.save(
            update_fields=[
                "website_config",
                "website_published_config",
                "website_draft_config",
                "website_onboarding_status",
                "website_onboarding_completed_at",
                "website_published_at",
                "is_website_published",
                "website_completion_percentage",
                "website_config_version",
            ]
        )
        return Response(WebsiteOnboardingSerializer(agency, context={"request": request}).data)


class WebsiteUnpublishView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        agency = getattr(request.user, "agency", None)
        if not agency or request.user.role not in ["agency_owner", "agency_manager"]:
            return Response(
                {"detail": "Only agency owners or managers can unpublish the website."},
                status=status.HTTP_403_FORBIDDEN,
            )
        agency.is_website_published = False
        agency.save(update_fields=["is_website_published"])
        return Response(WebsiteOnboardingSerializer(agency, context={"request": request}).data)


class TestMarkAgencyPaidView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = TestMarkAgencyPaidSerializer

    @extend_schema(
        request=TestMarkAgencyPaidSerializer,
        responses={
            200: TestMarkAgencyPaidSerializer,
        }
    )
    def post(self, request):
        if not settings.DEBUG:
            raise Http404()

        serializer = TestMarkAgencyPaidSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        license_number = serializer.validated_data["license_number"]
        verify_email = serializer.validated_data["verify_email"]

        user = User.objects.filter(
            email=email,
            agency__license_number=license_number
        ).select_related(
            "agency"
        ).first()

        if not user:
            return Response(
                {
                    "detail": "No user found for this email and license number."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        agency = user.agency

        agency.payment_status = Agency.PAYMENT_PAID
        agency.paid_at = timezone.now()
        agency.save(
            update_fields=[
                "payment_status",
                "paid_at",
            ]
        )

        if verify_email:
            user.is_email_verified = True
            user.save(
                update_fields=[
                    "is_email_verified",
                ]
            )

        return Response(
            {
                "message": "Test agency payment status updated.",
                "agency": {
                    "id": agency.id,
                    "name": agency.name,
                    "license_number": agency.license_number,
                    "payment_status": agency.payment_status,
                    "paid_at": agency.paid_at,
                },
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "role": user.role,
                    "is_email_verified": user.is_email_verified,
                },
            },
            status=status.HTTP_200_OK,
        )
