from django.db.models import Q
from django.shortcuts import get_object_or_404

from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response

from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
)
from drf_spectacular.types import OpenApiTypes

from users.models import AgencyUser
from .models import Property, PropertyMedia
from .serializers import PropertySerializer, PropertyMediaSerializer


PROPERTY_FILTER_PARAMETERS = [
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
            "agency"
        ).prefetch_related(
            "media"
        ).order_by("-created_at")

        property_type = self.request.query_params.get("property_type")
        status_value = self.request.query_params.get("status")
        location = self.request.query_params.get("location")
        assigned_agent = self.request.query_params.get("assigned_agent")

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

        return queryset

    def perform_create(self, serializer):
        serializer.save(
            agency=self.request.user.agency
        )


class PropertyFilterOptionsView(APIView):
    permission_classes = [IsAuthenticated]

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
            "agency"
        ).prefetch_related(
            "media"
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
        )