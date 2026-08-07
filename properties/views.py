from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied
from rest_framework import generics
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
)
from drf_spectacular.types import OpenApiTypes

from users.models import AgencyUser
from .models import Property, PropertyMedia, PropertyVerification, PropertyVerificationDocument
from .serializers import (
    PropertySerializer, PropertyMediaSerializer,
    PropertyVerificationSerializer, PropertyVerificationDocumentSerializer,
)
from .verification import get_or_create_verification


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
            serializer.save(
                agency=user.agency
            )
            return

        if is_agent(user):
            serializer.save(
                agency=user.agency,
                assigned_agent=user,
                status="draft",
                is_published=False,
                is_featured=False,
            )
            return

        raise PermissionDenied(
            "You do not have permission to create properties."
        )


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
        )

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

        return super().destroy(request, *args, **kwargs)


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


class PropertyVerificationDocumentDetailView(generics.RetrieveUpdateAPIView):
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
