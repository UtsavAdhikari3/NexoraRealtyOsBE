from django.db.models import Q

from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response

from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
)
from drf_spectacular.types import OpenApiTypes

from .models import Property
from .public_serializers import (
    PublicPropertySerializer,
    PublicPropertyInquirySerializer,
)
from django.db import transaction
from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response

from leads.models import Lead, LeadPropertyInterest, LeadInteraction


PUBLIC_PROPERTY_FILTER_PARAMETERS = [
    OpenApiParameter(
        name="property_type",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Filter by property type. Example: house, land, apartment"
    ),
    OpenApiParameter(
        name="purpose",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Filter by purpose. Example: sale, rent, lease"
    ),
    OpenApiParameter(
        name="location",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Search province, district, city, neighbourhood, and address"
    ),
    OpenApiParameter(
        name="price_min",
        type=OpenApiTypes.NUMBER,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Minimum price"
    ),
    OpenApiParameter(
        name="price_max",
        type=OpenApiTypes.NUMBER,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Maximum price"
    ),
    OpenApiParameter(
        name="bedrooms",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Minimum bedrooms"
    ),
    OpenApiParameter(
        name="bathrooms",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Minimum bathrooms"
    ),
    OpenApiParameter(
        name="featured",
        type=OpenApiTypes.BOOL,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Filter featured properties. Example: true"
    ),
    OpenApiParameter(
        name="search",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Search title, description, and location"
    ),
]


def get_public_properties_queryset(license_number):
    return Property.objects.filter(
        agency__license_number=license_number,
        agency__payment_status="paid",
        is_published=True,
        status="available",
    ).select_related(
        "agency",
        "assigned_agent",
    ).prefetch_related(
        "media",
    ).order_by(
        "-is_featured",
        "-published_at",
        "-created_at",
    )


@extend_schema_view(
    get=extend_schema(parameters=PUBLIC_PROPERTY_FILTER_PARAMETERS)
)
class PublicPropertyListView(generics.ListAPIView):
    serializer_class = PublicPropertySerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        queryset = get_public_properties_queryset(
            self.kwargs["license_number"]
        )

        property_type = self.request.query_params.get("property_type")
        purpose = self.request.query_params.get("purpose")
        location = self.request.query_params.get("location")
        price_min = self.request.query_params.get("price_min")
        price_max = self.request.query_params.get("price_max")
        bedrooms = self.request.query_params.get("bedrooms")
        bathrooms = self.request.query_params.get("bathrooms")
        featured = self.request.query_params.get("featured")
        search = self.request.query_params.get("search")

        if property_type and property_type != "all":
            queryset = queryset.filter(property_type=property_type)

        if purpose and purpose != "all":
            queryset = queryset.filter(purpose=purpose)

        if location and location != "all":
            queryset = queryset.filter(
                Q(province__icontains=location)
                | Q(district__icontains=location)
                | Q(city__icontains=location)
                | Q(neighbourhood__icontains=location)
                | Q(address__icontains=location)
            )

        if price_min:
            queryset = queryset.filter(price__gte=price_min)

        if price_max:
            queryset = queryset.filter(price__lte=price_max)

        if bedrooms and str(bedrooms).isdigit():
            queryset = queryset.filter(bedrooms__gte=int(bedrooms))

        if bathrooms and str(bathrooms).isdigit():
            queryset = queryset.filter(bathrooms__gte=int(bathrooms))

        if featured == "true":
            queryset = queryset.filter(is_featured=True)

        if search:
            queryset = queryset.filter(
                Q(title__icontains=search)
                | Q(short_description__icontains=search)
                | Q(description__icontains=search)
                | Q(province__icontains=search)
                | Q(district__icontains=search)
                | Q(city__icontains=search)
                | Q(neighbourhood__icontains=search)
                | Q(address__icontains=search)
            )

        return queryset


class PublicPropertyDetailView(generics.RetrieveAPIView):
    serializer_class = PublicPropertySerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return get_public_properties_queryset(
            self.kwargs["license_number"]
        )


class PublicPropertyFilterOptionsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, license_number):
        properties = get_public_properties_queryset(
            license_number
        ).only(
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

        return Response(
            {
                "property_types": [
                    {
                        "value": value,
                        "label": label
                    }
                    for value, label in Property.PROPERTY_TYPES
                ],
                "purposes": [
                    {
                        "value": value,
                        "label": label
                    }
                    for value, label in Property.PURPOSES
                ],
                "locations": location_values,
            }
        )
    
class PublicPropertyInquiryView(APIView):
    permission_classes = [AllowAny]
    serializer_class = PublicPropertyInquirySerializer

    @transaction.atomic
    def post(self, request, license_number, property_id):
        serializer = PublicPropertyInquirySerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)

        property_obj = get_object_or_404(
            Property,
            id=property_id,
            agency__license_number=license_number,
            agency__payment_status="paid",
            is_published=True,
            status="available",
        )

        data = serializer.validated_data

        lead = Lead.objects.create(
            agency=property_obj.agency,
            assigned_agent=property_obj.assigned_agent,
            full_name=data["full_name"],
            phone=data["phone"],
            email=data.get("email", ""),
            source="website",
            status="new",
            preferred_location=property_obj.city or property_obj.district,
            purpose=property_obj.purpose,
            property_type=property_obj.property_type,
            notes=data.get("message", ""),
        )

        lead_interest = LeadPropertyInterest.objects.create(
            agency=property_obj.agency,
            lead=lead,
            property=property_obj,
            interest_level="high",
            notes=data.get("message", ""),
        )

        lead_interaction = LeadInteraction.objects.create(
            agency=property_obj.agency,
            lead=lead,
            agent=property_obj.assigned_agent,
            interaction_type="note",
            note=data.get("message", "Public property inquiry submitted."),
        )

        return Response(
            {
                "message": "Inquiry submitted successfully.",
                "lead": {
                    "id": lead.id,
                    "full_name": lead.full_name,
                    "phone": lead.phone,
                    "email": lead.email,
                    "status": lead.status,
                    "source": lead.source,
                    "assigned_agent": lead.assigned_agent.id if lead.assigned_agent else None,
                },
                "property_interest": {
                    "id": lead_interest.id,
                    "property": property_obj.id,
                    "property_title": property_obj.title,
                    "interest_level": lead_interest.interest_level,
                },
                "interaction": {
                    "id": lead_interaction.id,
                    "interaction_type": lead_interaction.interaction_type,
                },
            },
            status=status.HTTP_201_CREATED,
        )
    
class PublicSimilarPropertiesView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, license_number, property_id):
        current_property = get_object_or_404(
            get_public_properties_queryset(license_number),
            id=property_id,
        )

        similar_properties = get_public_properties_queryset(
            license_number
        ).exclude(
            id=current_property.id
        ).filter(
            Q(property_type=current_property.property_type)
            | Q(purpose=current_property.purpose)
            | Q(city__iexact=current_property.city)
            | Q(district__iexact=current_property.district)
        ).distinct()[:6]

        serializer = PublicPropertySerializer(
            similar_properties,
            many=True,
            context={
                "request": request
            }
        )

        return Response(
            {
                "count": len(serializer.data),
                "results": serializer.data,
            }
        )