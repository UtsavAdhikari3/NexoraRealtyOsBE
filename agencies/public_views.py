from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Agency
from .public_serializers import (
    PublicAgencyContactSerializer,
    PublicAgencySerializer,
    PublicAgentSerializer,
)
from leads.models import LeadInteraction
from leads.services import get_or_create_public_lead

User = get_user_model()


def get_public_agencies_queryset():
    return Agency.objects.filter(
        payment_status=Agency.PAYMENT_PAID,
        is_active=True,
    ).filter(
        Q(subscription_expires_at__isnull=True)
        | Q(subscription_expires_at__gt=timezone.now())
    )


class PublicAgencyDetailView(generics.RetrieveAPIView):
    serializer_class = PublicAgencySerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    lookup_field = "license_number"
    lookup_url_kwarg = "license_number"

    def get_queryset(self):
        return get_public_agencies_queryset()


class PublicAgencySlugDetailView(PublicAgencyDetailView):
    lookup_field = "slug"
    lookup_url_kwarg = "slug"


class PublicAgentListView(generics.ListAPIView):
    serializer_class = PublicAgentSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    pagination_class = None

    def get_queryset(self):
        agency = get_object_or_404(
            get_public_agencies_queryset(),
            license_number=self.kwargs["license_number"],
        )
        return User.objects.filter(
            agency=agency,
            role=User.ROLE_AGENT,
            is_active=True,
        ).prefetch_related("assigned_properties").order_by("full_name")


class PublicAgentDetailView(generics.RetrieveAPIView):
    serializer_class = PublicAgentSerializer
    permission_classes = [AllowAny]
    authentication_classes = []

    def get_queryset(self):
        agency = get_object_or_404(
            get_public_agencies_queryset(),
            license_number=self.kwargs["license_number"],
        )
        return User.objects.filter(
            agency=agency,
            role=User.ROLE_AGENT,
            is_active=True,
        ).prefetch_related("assigned_properties")


class PublicAgencyContactView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "public_submission"
    serializer_class = PublicAgencyContactSerializer

    @transaction.atomic
    def post(self, request, license_number):
        agency = get_object_or_404(
            get_public_agencies_queryset(),
            license_number=license_number,
        )
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
