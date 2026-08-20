from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.core import signing
from urllib.parse import urlparse

from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Agency, AgencyDomain
from .public_selectors import get_public_agency, public_agencies
from .public_serializers import (
    PublicAgencyContactSerializer,
    PublicAgencySerializer,
    PublicAgentSerializer,
)
from leads.models import LeadInteraction
from leads.services import get_or_create_public_lead

User = get_user_model()


def get_public_agencies_queryset():
    """Compatibility alias for callers moving to the shared selector."""
    return public_agencies()


class PublicAgencyDetailView(generics.RetrieveAPIView):
    serializer_class = PublicAgencySerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    lookup_field = "license_number"
    lookup_url_kwarg = "license_number"

    def get_queryset(self):
        return get_public_agencies_queryset()

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        etag = f'"agency-{instance.pk}-v{instance.website_config_version}"'
        if request.headers.get("If-None-Match") == etag:
            response = Response(status=status.HTTP_304_NOT_MODIFIED)
        else:
            response = Response(self.get_serializer(instance).data)
        response["ETag"] = etag
        response["Cache-Control"] = "public, max-age=60, must-revalidate"
        return response


class PublicAgencySlugDetailView(PublicAgencyDetailView):
    lookup_field = "slug"
    lookup_url_kwarg = "slug"


class PublicAgencyDomainDetailView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = PublicAgencySerializer

    def get(self, request):
        raw_domain = request.query_params.get("domain", "").strip().lower()
        if not raw_domain:
            return Response(
                {"domain": ["This query parameter is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        parsed = urlparse(raw_domain if "://" in raw_domain else f"//{raw_domain}")
        domain = (parsed.hostname or raw_domain).rstrip(".")
        claimed = get_object_or_404(
            AgencyDomain.objects.select_related("agency"),
            domain=domain,
            status=AgencyDomain.STATUS_VERIFIED,
            is_active=True,
        )
        agency = get_object_or_404(get_public_agencies_queryset(), pk=claimed.agency_id)
        return Response(self.serializer_class(agency, context={"request": request}).data)


class PublicAgencyPreviewView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = PublicAgencySerializer

    def get(self, request):
        token = request.query_params.get("token", "")
        try:
            payload = signing.loads(
                token,
                salt="agency-website-preview",
                max_age=60 * 60 * 24,
            )
            agency = Agency.objects.get(pk=payload["agency_id"], is_active=True)
        except (signing.BadSignature, signing.SignatureExpired, Agency.DoesNotExist, KeyError, TypeError):
            return Response({"detail": "This website preview link is invalid or expired."}, status=status.HTTP_404_NOT_FOUND)

        agency.website_published_config = agency.website_draft_config or agency.website_published_config or agency.website_config
        return Response(self.serializer_class(agency, context={"request": request}).data)


class PublicAgentListView(generics.ListAPIView):
    serializer_class = PublicAgentSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    pagination_class = None

    def get_queryset(self):
        agency = get_public_agency(license_number=self.kwargs["license_number"])
        return User.objects.filter(
            agency=agency,
            role=User.ROLE_AGENT,
            is_active=True,
        ).prefetch_related("assigned_properties", "public_reviews").order_by("full_name")


class PublicAgentDetailView(generics.RetrieveAPIView):
    serializer_class = PublicAgentSerializer
    permission_classes = [AllowAny]
    authentication_classes = []

    def get_queryset(self):
        agency = get_public_agency(license_number=self.kwargs["license_number"])
        return User.objects.filter(
            agency=agency,
            role=User.ROLE_AGENT,
            is_active=True,
        ).prefetch_related("assigned_properties", "public_reviews")


class PublicAgencyContactView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "public_submission"
    serializer_class = PublicAgencyContactSerializer

    @transaction.atomic
    def post(self, request, license_number):
        agency = get_public_agency(license_number=license_number)
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        lead, created = get_or_create_public_lead(
            agency=agency,
            full_name=data["full_name"],
            phone=data["phone"],
            email=data.get("email", ""),
            notes=data.get("message", ""),
        )
        LeadInteraction.objects.create(
            agency=agency,
            lead=lead,
            interaction_type="note",
            direction="inbound",
            note=data.get("message") or "Public agency contact form submitted.",
        )

        return Response(
            {
                "message": "Contact request submitted successfully.",
                "lead_id": lead.id,
                "created": created,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
