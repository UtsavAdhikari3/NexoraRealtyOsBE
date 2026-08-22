from django.db import transaction
from django.db.models import Count, Q
from django.core.files.base import ContentFile
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework import generics
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from users.permissions import (
    is_agency_owner_or_manager,
    is_agent,
)
from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
    OpenApiResponse,
)
from drf_spectacular.types import OpenApiTypes

from users.models import AgencyUser
from .models import (
    Property, PropertyMedia, PropertyVerification, PropertyVerificationDocument,
    PropertyHistory, PropertyDuplicateFlag,
    PropertyDistributionLink, PropertyEvent,
)
from .serializers import (
    PropertySerializer, PropertyMediaSerializer,
    PropertyVerificationSerializer, PropertyVerificationDocumentSerializer,
    PropertyHistorySerializer, PropertyDuplicateFlagSerializer,
    PropertyDistributionLinkSerializer,
    PropertyDistributionSocialDraftRequestSerializer,
)
from .verification import get_or_create_verification, reconcile_verification
from .freshness import (
    confirm_listing_freshness, detect_duplicate_listings, record_property_history,
)
from django.utils import timezone
from datetime import timedelta
from social_media.serializers import SocialPostSerializer


PROPERTY_FILTER_PARAMETERS = [
    OpenApiParameter(
        name="search",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Search by property ID, title, or location",
    ),
    OpenApiParameter(
        name="property_type",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Filter by property type. Example: house, land, apartment, flat, commercial, office_space",
    ),
    OpenApiParameter(
        name="status",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Filter by property status. Example: draft, available, under_negotiation, sold, rented, hidden, archived",
    ),
    OpenApiParameter(
        name="location",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Search location across province, district, city, neighbourhood, and address",
    ),
    OpenApiParameter(
        name="assigned_agent",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Filter by assigned agent ID, or use 'unassigned'",
    ),
]
AGENT_BLOCKED_PROPERTY_FIELDS = {
    "agency",
    "assigned_agent",
    "status",
    "is_published",
    "is_featured",
    "published_at",
}


def can_manage_any_property(user):
    return is_agency_owner_or_manager(user)


def can_agent_manage_property(user, property_obj):
    return (
        is_agent(user)
        and property_obj.assigned_agent_id == user.id
    )


def can_manage_property(user, property_obj):
    return (
        can_manage_any_property(user)
        or can_agent_manage_property(user, property_obj)
    )


def validate_agent_property_update(request):
    blocked_fields = AGENT_BLOCKED_PROPERTY_FIELDS.intersection(
        set(request.data.keys())
    )

    if blocked_fields:
        blocked_list = ", ".join(sorted(blocked_fields))

        raise PermissionDenied(
            f"Agents cannot update these fields: {blocked_list}"
        )

@extend_schema_view(
    get=extend_schema(parameters=PROPERTY_FILTER_PARAMETERS)
)
class PropertyListCreateView(generics.ListCreateAPIView):
    serializer_class = PropertySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Property.objects.filter(
            agency=self.request.user.agency
        ).select_related(
            "assigned_agent",
            "agency",
            "verification",
        ).prefetch_related(
            "media",
            "verification__documents",
            "duplicate_flags",
        ).order_by("-created_at")

        property_type = self.request.query_params.get("property_type")
        status_value = self.request.query_params.get("status")
        location = self.request.query_params.get("location")
        assigned_agent = self.request.query_params.get("assigned_agent")
        search = self.request.query_params.get("search", "").strip()

        if property_type and property_type != "all":
            queryset = queryset.filter(property_type=property_type)

        if status_value and status_value != "all":
            queryset = queryset.filter(status=status_value)

        if location and location != "all":
            queryset = queryset.filter(
                Q(province__icontains=location)
                | Q(district__icontains=location)
                | Q(city__icontains=location)
                | Q(neighbourhood__icontains=location)
                | Q(address__icontains=location)
            )

        if assigned_agent and assigned_agent != "all":
            if assigned_agent == "unassigned":
                queryset = queryset.filter(assigned_agent__isnull=True)
            elif assigned_agent.isdigit():
                queryset = queryset.filter(assigned_agent_id=int(assigned_agent))
            else:
                queryset = queryset.none()

        if search:
            if search.isdigit():
                search_query = Q(pk=int(search))
            else:
                search_query = (
                    Q(title__icontains=search)
                    | Q(province__icontains=search)
                    | Q(district__icontains=search)
                    | Q(city__icontains=search)
                    | Q(neighbourhood__icontains=search)
                    | Q(address__icontains=search)
                )
            queryset = queryset.filter(search_query)

        return queryset

    def perform_create(self, serializer):
        user = self.request.user

        if is_agency_owner_or_manager(user):
            property_obj = serializer.save(
                agency=user.agency
            )
        elif is_agent(user):
            property_obj = serializer.save(
                agency=user.agency,
                assigned_agent=user,
                status="draft",
                is_published=False,
                is_featured=False,
            )
        else:
            raise PermissionDenied("You do not have permission to create properties.")
        record_property_history(property_obj, "created", "Property listing created", actor=user)
        detect_duplicate_listings(property_obj)


class PropertyFilterOptionsView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PropertySerializer

    def get(self, request):
        agency = request.user.agency

        properties = Property.objects.filter(
            agency=agency
        ).only(
            "province",
            "district",
            "city",
            "neighbourhood",
        ).order_by(
            "province",
            "district",
            "city",
            "neighbourhood",
        )

        location_values = []
        seen_locations = set()

        def add_location(value, location_type):
            if not value:
                return

            cleaned_value = value.strip()

            if not cleaned_value:
                return

            if cleaned_value in seen_locations:
                return

            seen_locations.add(cleaned_value)

            location_values.append(
                {
                    "value": cleaned_value,
                    "label": cleaned_value,
                    "type": location_type,
                }
            )

        for property_obj in properties:
            add_location(property_obj.province, "province")
            add_location(property_obj.district, "district")
            add_location(property_obj.city, "city")
            add_location(property_obj.neighbourhood, "neighbourhood")

        agents = AgencyUser.objects.filter(
            agency=agency,
            role="agent",
            is_active=True
        ).order_by("full_name")

        return Response(
            {
                "property_types": [
                    {
                        "value": value,
                        "label": label
                    }
                    for value, label in Property.PROPERTY_TYPES
                ],

                "statuses": [
                    {
                        "value": value,
                        "label": label
                    }
                    for value, label in Property.STATUS_CHOICES
                ],

                "locations": location_values,

                "agents": [
                    {
                        "value": agent.id,
                        "label": agent.full_name
                    }
                    for agent in agents
                ] + [
                    {
                        "value": "unassigned",
                        "label": "Unassigned"
                    }
                ],
            }
        )


class PropertyDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PropertySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Property.objects.filter(
            agency=self.request.user.agency
        ).select_related(
            "assigned_agent",
            "agency",
            "verification",
        ).prefetch_related(
            "media",
            "verification__documents",
            "duplicate_flags",
        )

    def perform_update(self, serializer):
        instance = serializer.instance
        changes = {}
        for field, value in serializer.validated_data.items():
            previous = getattr(instance, field, None)
            if previous != value:
                changes[field] = {"from": str(previous) if previous is not None else None, "to": str(value) if value is not None else None}
        previous_status = instance.status
        property_obj = serializer.save()
        if changes:
            event_type = "withdrawn" if property_obj.status == "withdrawn" else "status_changed" if previous_status != property_obj.status else "updated"
            summary = "Property withdrawn" if event_type == "withdrawn" else "Property status changed" if event_type == "status_changed" else "Property listing updated"
            record_property_history(
                property_obj, event_type, summary, actor=self.request.user,
                changes=changes, note=property_obj.withdrawal_reason if event_type == "withdrawn" else "",
            )
        detect_duplicate_listings(property_obj)

    def update(self, request, *args, **kwargs):
        property_obj = self.get_object()
        user = request.user

        if is_agency_owner_or_manager(user):
            return super().update(request, *args, **kwargs)

        if can_agent_manage_property(user, property_obj):
            validate_agent_property_update(request)
            return super().update(request, *args, **kwargs)

        raise PermissionDenied(
            "You do not have permission to update this property."
        )

    def partial_update(self, request, *args, **kwargs):
        property_obj = self.get_object()
        user = request.user

        if is_agency_owner_or_manager(user):
            return super().partial_update(request, *args, **kwargs)

        if can_agent_manage_property(user, property_obj):
            validate_agent_property_update(request)
            return super().partial_update(request, *args, **kwargs)

        raise PermissionDenied(
            "You do not have permission to update this property."
        )

    def destroy(self, request, *args, **kwargs):
        if is_agency_owner_or_manager(request.user):
            return super().destroy(request, *args, **kwargs)

        raise PermissionDenied(
            "Only agency owners or managers can delete properties."
        )

class PropertyMediaListCreateView(generics.ListCreateAPIView):
    serializer_class = PropertyMediaSerializer
    permission_classes = [IsAuthenticated]

    def get_property(self):
        return get_object_or_404(
            Property,
            id=self.kwargs["property_id"],
            agency=self.request.user.agency
        )

    def get_queryset(self):
        property_obj = self.get_property()

        return PropertyMedia.objects.filter(
            agency=self.request.user.agency,
            property=property_obj
        ).order_by("sort_order", "-created_at")

    def perform_create(self, serializer):
        property_obj = self.get_property()

        if not can_manage_property(self.request.user, property_obj):
            raise PermissionDenied(
                "You do not have permission to upload media for this property."
            )

        serializer.save(
            agency=self.request.user.agency,
            property=property_obj,
            uploaded_by=self.request.user,
        )


class PropertyMediaDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PropertyMediaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PropertyMedia.objects.filter(
            agency=self.request.user.agency
        ).select_related(
            "property",
            "agency",
            "uploaded_by",
        )

    def update(self, request, *args, **kwargs):
        media = self.get_object()

        if not can_manage_property(request.user, media.property):
            raise PermissionDenied(
                "You do not have permission to update this media."
            )

        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        media = self.get_object()

        if not can_manage_property(request.user, media.property):
            raise PermissionDenied(
                "You do not have permission to update this media."
            )

        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        media = self.get_object()

        if not can_manage_property(request.user, media.property):
            raise PermissionDenied(
                "You do not have permission to delete this media."
            )

        property_id = media.property_id
        was_primary = media.is_primary
        with transaction.atomic():
            response = super().destroy(request, *args, **kwargs)
            if was_primary:
                replacement = PropertyMedia.objects.filter(
                    property_id=property_id,
                    media_type="image",
                ).order_by("sort_order", "id").first()
                if replacement:
                    replacement.is_primary = True
                    replacement.save(update_fields=["is_primary"])
        return response


class PropertyVerificationDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = PropertyVerificationSerializer
    permission_classes = [IsAuthenticated]

    def get_property(self):
        return get_object_or_404(
            Property.objects.select_related("agency", "assigned_agent"),
            id=self.kwargs["property_id"],
            agency=self.request.user.agency,
        )

    def get_object(self):
        property_obj = self.get_property()
        verification = get_or_create_verification(property_obj)
        return PropertyVerification.objects.prefetch_related(
            "documents", "documents__reviewed_by"
        ).select_related("updated_by").get(pk=verification.pk)

    def update(self, request, *args, **kwargs):
        if not can_manage_property(request.user, self.get_property()):
            raise PermissionDenied("You do not have permission to update property verification.")
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        if not can_manage_property(request.user, self.get_property()):
            raise PermissionDenied("You do not have permission to update property verification.")
        return super().partial_update(request, *args, **kwargs)

    def perform_update(self, serializer):
        instance = serializer.instance
        before = {
            field: getattr(instance, field)
            for field, _ in PropertyVerification.MILESTONES
        }
        verification = serializer.save()
        changes = {
            field: {"from": before[field], "to": getattr(verification, field)}
            for field in before
            if before[field] != getattr(verification, field)
        }
        if changes:
            record_property_history(
                verification.property,
                "verification_changed",
                "Property verification milestones updated",
                actor=self.request.user,
                changes=changes,
            )


class PropertyVerificationDocumentDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PropertyVerificationDocumentSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "document_type"
    lookup_url_kwarg = "document_type"

    def get_property(self):
        return get_object_or_404(
            Property,
            id=self.kwargs["property_id"],
            agency=self.request.user.agency,
        )

    def get_queryset(self):
        property_obj = self.get_property()
        verification = get_or_create_verification(property_obj)
        return PropertyVerificationDocument.objects.filter(
            verification=verification,
            agency=self.request.user.agency,
        ).select_related("reviewed_by", "verification__property")

    def update(self, request, *args, **kwargs):
        if not can_manage_property(request.user, self.get_property()):
            raise PermissionDenied("You do not have permission to update verification documents.")
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        if not can_manage_property(request.user, self.get_property()):
            raise PermissionDenied("You do not have permission to update verification documents.")
        return super().partial_update(request, *args, **kwargs)

    def perform_update(self, serializer):
        instance = serializer.instance
        before = {
            "status": instance.status,
            "file": instance.file.name if instance.file else "",
            "external_url": instance.external_url,
        }
        document = serializer.save()
        after = {
            "status": document.status,
            "file": document.file.name if document.file else "",
            "external_url": document.external_url,
        }
        changes = {
            key: {"from": before[key], "to": after[key]}
            for key in before if before[key] != after[key]
        }
        if changes:
            record_property_history(
                document.verification.property,
                "document_changed",
                f"{document.get_document_type_display()} updated",
                actor=self.request.user,
                changes=changes,
            )
        reconcile_verification(
            document.verification,
            actor=self.request.user,
            reason=f"{document.get_document_type_display()} was updated",
        )

    def destroy(self, request, *args, **kwargs):
        property_obj = self.get_property()
        if not can_manage_property(request.user, property_obj):
            raise PermissionDenied("You do not have permission to delete verification documents.")
        document = self.get_object()
        if document.file:
            document.file.delete(save=False)
        document.file = None
        document.external_url = ""
        document.document_number = ""
        document.issued_date = None
        document.expiry_date = None
        document.notes = ""
        document.status = "missing"
        document.reviewed_by = None
        document.reviewed_at = None
        document.save()
        record_property_history(
            property_obj,
            "document_changed",
            f"{document.get_document_type_display()} removed from verification checklist",
            actor=request.user,
        )
        reconcile_verification(
            document.verification,
            actor=request.user,
            reason=f"{document.get_document_type_display()} was removed",
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class PropertyFreshnessConfirmView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, property_id):
        property_obj = get_object_or_404(Property, id=property_id, agency=request.user.agency)
        if not can_manage_property(request.user, property_obj):
            raise PermissionDenied("You do not have permission to confirm this listing.")
        try:
            valid_for_days = int(request.data.get("valid_for_days", 30))
        except (TypeError, ValueError):
            raise ValidationError({"valid_for_days": "Enter a whole number of days."})
        if valid_for_days < 1 or valid_for_days > 90:
            raise ValidationError({"valid_for_days": "Choose between 1 and 90 days."})
        confirm_listing_freshness(
            property_obj, request.user, valid_for_days,
            owner_confirmed=bool(request.data.get("owner_confirmed", False)),
        )
        return Response(PropertySerializer(property_obj, context={"request": request}).data)


class PropertyRepublishRequestView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, property_id):
        property_obj = get_object_or_404(
            Property.objects.select_for_update(),
            id=property_id, agency=request.user.agency,
        )
        if not can_manage_property(request.user, property_obj):
            raise PermissionDenied("You do not have permission to request republication.")
        if not property_obj.requires_republish_approval:
            raise ValidationError({"detail": "This listing does not require republish approval."})
        property_obj.republish_approval_status = "pending"
        property_obj.republish_requested_at = timezone.now()
        property_obj.republish_requested_by = request.user
        property_obj.republish_rejection_reason = ""
        property_obj.is_published = False
        property_obj.save(update_fields=[
            "republish_approval_status", "republish_requested_at", "republish_requested_by",
            "republish_rejection_reason", "is_published", "updated_at",
        ])
        record_property_history(property_obj, "republish_requested", "Manager approval requested for republication", actor=request.user)
        return Response(PropertySerializer(property_obj, context={"request": request}).data)


class PropertyRepublishDecisionView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, property_id):
        if not is_agency_owner_or_manager(request.user):
            raise PermissionDenied("Only agency owners or managers can approve republication.")
        property_obj = get_object_or_404(
            Property.objects.select_for_update(),
            id=property_id, agency=request.user.agency,
        )
        if property_obj.republish_approval_status != "pending":
            raise ValidationError({"detail": "No republish request is pending."})
        decision = request.data.get("decision")
        if decision not in {"approve", "reject"}:
            raise ValidationError({"decision": "Choose approve or reject."})
        if decision == "approve":
            now = timezone.now()
            property_obj.availability_verified_at = now
            property_obj.listing_expires_at = now + timedelta(days=30)
            property_obj.requires_republish_approval = False
            property_obj.republish_approval_status = "approved"
            property_obj.republish_approved_at = now
            property_obj.republish_approved_by = request.user
            property_obj.republish_rejection_reason = ""
            property_obj.is_published = property_obj.status in {"available", "reserved", "under_negotiation"}
            event_type, summary = "republish_approved", "Republication approved by manager"
        else:
            reason = str(request.data.get("reason", "")).strip()
            if not reason:
                raise ValidationError({"reason": "Provide a rejection reason."})
            property_obj.republish_approval_status = "rejected"
            property_obj.republish_rejection_reason = reason
            property_obj.is_published = False
            event_type, summary = "republish_rejected", "Republication rejected by manager"
        property_obj.save()
        record_property_history(property_obj, event_type, summary, actor=request.user, note=property_obj.republish_rejection_reason)
        return Response(PropertySerializer(property_obj, context={"request": request}).data)


class PropertyHistoryListView(generics.ListAPIView):
    serializer_class = PropertyHistorySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        return PropertyHistory.objects.filter(
            property_id=self.kwargs["property_id"], agency=self.request.user.agency,
        ).select_related("actor")


class PropertyDuplicateFlagListView(generics.ListAPIView):
    serializer_class = PropertyDuplicateFlagSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        property_obj = get_object_or_404(Property, id=self.kwargs["property_id"], agency=self.request.user.agency)
        detect_duplicate_listings(property_obj)
        return PropertyDuplicateFlag.objects.filter(property=property_obj).select_related("candidate", "reviewed_by")


class PropertyDuplicateFlagDetailView(generics.UpdateAPIView):
    serializer_class = PropertyDuplicateFlagSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PropertyDuplicateFlag.objects.filter(agency=self.request.user.agency).select_related("property", "candidate")

    def perform_update(self, serializer):
        flag = serializer.instance
        if not can_manage_property(self.request.user, flag.property):
            raise PermissionDenied("You do not have permission to review this duplicate flag.")
        if serializer.validated_data.get("status") not in {"confirmed", "dismissed"}:
            raise ValidationError({"status": "Choose confirmed or dismissed."})
        serializer.save(reviewed_by=self.request.user, reviewed_at=timezone.now())


def get_distribution_property(request, property_id):
    property_obj = get_object_or_404(
        Property.objects.select_related("agency", "assigned_agent").prefetch_related("media"),
        id=property_id,
        agency=request.user.agency,
    )
    if not can_manage_property(request.user, property_obj):
        raise PermissionDenied("You do not have permission to distribute this property.")
    return property_obj


class PropertyDistributionToolkitView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, property_id):
        from .distribution import (
            ASSET_SPECS, canonical_property_url, captions, portal_ad,
        )

        property_obj = get_distribution_property(request, property_id)
        public_url = canonical_property_url(property_obj)
        links = property_obj.distribution_links.select_related("created_by").all()
        event_summary = list(
            property_obj.events.exclude(utm_source="").values("utm_source").annotate(
                total=Count("id"),
                inquiries=Count("id", filter=Q(event_type=PropertyEvent.EVENT_INQUIRY)),
                site_visits=Count("id", filter=Q(event_type=PropertyEvent.EVENT_SITE_VISIT_REQUEST)),
            ).order_by("-total")
        )
        return Response({
            "property": {
                "id": property_obj.id,
                "display_property_id": f"LP-{property_obj.id:03d}",
                "title": property_obj.title,
                "status": property_obj.status,
            },
            "public_url": public_url,
            "captions": captions(property_obj, public_url),
            "portal_ad": {
                "english": portal_ad(property_obj, public_url),
                "nepali": portal_ad(property_obj, public_url, "nepali"),
            },
            "assets": [
                {"type": key, "label": spec[2], "extension": spec[3]}
                for key, spec in ASSET_SPECS.items()
            ],
            "links": PropertyDistributionLinkSerializer(
                links, many=True, context={"request": request}
            ).data,
            "attribution": event_summary,
        })


class PropertyDistributionLinkListCreateView(generics.ListCreateAPIView):
    serializer_class = PropertyDistributionLinkSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_property(self):
        return get_distribution_property(self.request, self.kwargs["property_id"])

    def get_queryset(self):
        return PropertyDistributionLink.objects.filter(
            agency=self.request.user.agency,
            property=self.get_property(),
        ).select_related("created_by")

    def perform_create(self, serializer):
        serializer.save(
            agency=self.request.user.agency,
            property=self.get_property(),
            created_by=self.request.user,
            is_active=True,
        )


class PropertyDistributionLinkDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PropertyDistributionLinkSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PropertyDistributionLink.objects.filter(
            agency=self.request.user.agency
        ).select_related("property", "created_by")

    def get_object(self):
        obj = super().get_object()
        if not can_manage_property(self.request.user, obj.property):
            raise PermissionDenied("You do not have permission to manage this link.")
        return obj


class PropertyDistributionAssetView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, property_id, asset_type):
        from .distribution import (
            ASSET_SPECS, brochure_pdf, canonical_property_url, media_package,
            portal_csv, qr_png, social_image, tracked_url, watermarked_zip,
            window_card_pdf,
        )

        if asset_type not in ASSET_SPECS:
            raise ValidationError({"asset_type": "Unknown distribution asset."})
        property_obj = get_distribution_property(request, property_id)
        language = request.query_params.get("language", property_obj.agency.default_language)
        date_system = request.query_params.get("date_system", property_obj.agency.default_date_system)
        nepali_digits = request.query_params.get(
            "nepali_digits", str(property_obj.agency.use_nepali_digits)
        ).lower() in {"1", "true", "yes"}
        if language not in {"en", "ne"}:
            raise ValidationError({"language": "Choose en or ne."})
        if date_system not in {"ad", "bs"}:
            raise ValidationError({"date_system": "Choose ad or bs."})
        link = None
        if request.query_params.get("link"):
            link = get_object_or_404(
                PropertyDistributionLink,
                id=request.query_params["link"],
                property=property_obj,
                agency=request.user.agency,
                is_active=True,
            )
        url = tracked_url(link, request) if link else canonical_property_url(property_obj)
        stem = f"LP-{property_obj.id:03d}-{asset_type}"
        if asset_type in {"facebook_post", "instagram_post", "instagram_story"}:
            response = HttpResponse(social_image(property_obj, asset_type, url), content_type="image/jpeg")
            filename = f"{stem}.jpg"
        elif asset_type == "qr_code":
            response = HttpResponse(qr_png(url), content_type="image/png")
            filename = f"{stem}.png"
        elif asset_type == "brochure":
            response = HttpResponse(
                brochure_pdf(property_obj, url, language, date_system, nepali_digits),
                content_type="application/pdf",
            )
            filename = f"{stem}.pdf"
        elif asset_type == "window_card":
            response = HttpResponse(
                window_card_pdf(property_obj, url, language, date_system, nepali_digits),
                content_type="application/pdf",
            )
            filename = f"{stem}.pdf"
        elif asset_type == "portal_csv":
            response = HttpResponse(portal_csv([property_obj], request), content_type="text/csv; charset=utf-8")
            filename = f"{stem}.csv"
        elif asset_type == "watermarked_images":
            response = FileResponse(watermarked_zip(property_obj), content_type="application/zip")
            filename = f"{stem}.zip"
        else:
            response = FileResponse(
                media_package(property_obj, url, language, date_system, nepali_digits),
                content_type="application/zip",
            )
            filename = f"{stem}.zip"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class PropertyPortalExportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .distribution import portal_csv

        queryset = Property.objects.filter(agency=request.user.agency).select_related(
            "agency", "assigned_agent"
        ).order_by("id")
        if not can_manage_any_property(request.user):
            queryset = queryset.filter(assigned_agent=request.user)
        ids = [value for value in request.query_params.get("ids", "").split(",") if value.isdigit()]
        if ids:
            queryset = queryset.filter(id__in=ids)
        response = HttpResponse(portal_csv(queryset, request), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="nexora-property-portal-export.csv"'
        return response


class PropertyDistributionSocialDraftView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=PropertyDistributionSocialDraftRequestSerializer,
        responses={
            201: OpenApiResponse(
                response=SocialPostSerializer,
                description="Generated social draft",
            )
        },
        description=(
            "Generate a branded property social draft. Publishing is intentionally "
            "performed separately through /api/social-posts/posts/{id}/publish/."
        ),
    )
    def post(self, request, property_id):
        from social_media.models import SocialAccount, SocialPost
        from .distribution import captions, canonical_property_url, social_image, tracked_url

        request_serializer = PropertyDistributionSocialDraftRequestSerializer(
            data=request.data
        )
        request_serializer.is_valid(raise_exception=True)
        payload = request_serializer.validated_data
        property_obj = get_distribution_property(request, property_id)
        account = get_object_or_404(
            SocialAccount,
            id=payload["social_account"],
            agency=request.user.agency,
            status=SocialAccount.STATUS_CONNECTED,
        )
        target_platforms = payload.get("platforms") or [account.platform]
        for target_platform in target_platforms:
            if target_platform == account.platform:
                continue
            if not SocialAccount.objects.filter(
                agency=request.user.agency,
                provider=SocialAccount.PROVIDER_META,
                platform=target_platform,
                page_id=account.page_id,
                status=SocialAccount.STATUS_CONNECTED,
            ).exists():
                raise ValidationError(
                    {
                        "platforms": (
                            f"No connected {target_platform} account is linked "
                            "to the selected Page."
                        )
                    }
                )
        asset_type = payload.get("asset_type") or (
            "facebook_post" if account.platform == "facebook" else "instagram_post"
        )
        valid_asset = "facebook_post" if account.platform == "facebook" else "instagram_post"
        if asset_type != valid_asset:
            raise ValidationError({"asset_type": f"Use {valid_asset} for this account."})
        language = payload["language"]
        link = None
        if payload.get("link"):
            link = get_object_or_404(
                PropertyDistributionLink,
                id=payload["link"], property=property_obj,
                agency=request.user.agency, is_active=True,
            )
        url = tracked_url(link, request) if link else canonical_property_url(property_obj)
        image_bytes = social_image(property_obj, asset_type, url)
        post = SocialPost(
            agency=request.user.agency,
            property=property_obj,
            social_account=account,
            platform=account.platform,
            target_platforms=target_platforms,
            caption=captions(property_obj, url)[language][account.platform],
            status=SocialPost.STATUS_DRAFT,
            created_by=request.user,
        )
        post.image.save(f"LP-{property_obj.id:03d}-{asset_type}.jpg", ContentFile(image_bytes), save=False)
        post.save()
        return Response(
            SocialPostSerializer(post, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )
