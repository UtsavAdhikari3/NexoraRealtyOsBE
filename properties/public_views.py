from django.db.models import Q
from django.utils import timezone
from decimal import Decimal, InvalidOperation

from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
)
from drf_spectacular.types import OpenApiTypes

from .models import Property, PropertyEvent
from .area import convert_area
from .public_serializers import (
    PublicPropertyEventSerializer,
    PublicPropertySerializer,
    PublicPropertyInquirySerializer,
)
from django.db import transaction
from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response

from leads.models import LeadPropertyInterest, LeadInteraction
from leads.services import get_or_create_public_lead


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
        agency__is_active=True,
        is_published=True,
        status="available",
    ).filter(
        Q(agency__subscription_expires_at__isnull=True)
        | Q(agency__subscription_expires_at__gt=timezone.now())
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


def parse_decimal_filter(value, field_name):
    if value in [None, ""]:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValidationError({field_name: "Enter a valid number."})


@extend_schema_view(
    get=extend_schema(parameters=PUBLIC_PROPERTY_FILTER_PARAMETERS)
)
class PublicPropertyListView(generics.ListAPIView):
    serializer_class = PublicPropertySerializer
    permission_classes = [AllowAny]
    authentication_classes = []

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
        province = self.request.query_params.get("province")
        district = self.request.query_params.get("district")
        city = self.request.query_params.get("city")
        municipality = self.request.query_params.get("municipality")
        ward_number = self.request.query_params.get("ward_number")
        classification = self.request.query_params.get("land_use_classification")
        road_type = self.request.query_params.get("road_type")
        plot_shape = self.request.query_params.get("plot_shape")
        utility_filters = {
            "has_water_supply": self.request.query_params.get("has_water_supply"),
            "has_electricity": self.request.query_params.get("has_electricity"),
            "has_drainage": self.request.query_params.get("has_drainage"),
            "has_sewage": self.request.query_params.get("has_sewage"),
        }
        furnishing = self.request.query_params.get("furnishing_status")
        facing = self.request.query_params.get("facing_direction")
        land_area_min = self.request.query_params.get("land_area_min")
        land_area_max = self.request.query_params.get("land_area_max")
        land_area_unit = self.request.query_params.get("land_area_unit", "aana")
        road_access_min = self.request.query_params.get("road_access_min")
        ordering = self.request.query_params.get("ordering")
        min_lat = self.request.query_params.get("min_lat")
        max_lat = self.request.query_params.get("max_lat")
        min_lng = self.request.query_params.get("min_lng")
        max_lng = self.request.query_params.get("max_lng")

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
                | Q(municipality__icontains=location)
                | Q(tole__icontains=location)
                | Q(landmark__icontains=location)
                | Q(address__icontains=location)
            )

        price_min = parse_decimal_filter(price_min, "price_min")
        price_max = parse_decimal_filter(price_max, "price_max")
        land_area_min = parse_decimal_filter(land_area_min, "land_area_min")
        land_area_max = parse_decimal_filter(land_area_max, "land_area_max")
        road_access_min = parse_decimal_filter(road_access_min, "road_access_min")
        min_lat = parse_decimal_filter(min_lat, "min_lat")
        max_lat = parse_decimal_filter(max_lat, "max_lat")
        min_lng = parse_decimal_filter(min_lng, "min_lng")
        max_lng = parse_decimal_filter(max_lng, "max_lng")

        if price_min is not None:
            queryset = queryset.filter(price__gte=price_min)

        if price_max is not None:
            queryset = queryset.filter(price__lte=price_max)

        if bedrooms and str(bedrooms).isdigit():
            queryset = queryset.filter(bedrooms__gte=int(bedrooms))

        if bathrooms and str(bathrooms).isdigit():
            queryset = queryset.filter(bathrooms__gte=int(bathrooms))

        if featured == "true":
            queryset = queryset.filter(is_featured=True)

        if province:
            queryset = queryset.filter(province__iexact=province)
        if district:
            queryset = queryset.filter(district__iexact=district)
        if city:
            queryset = queryset.filter(city__iexact=city)
        if municipality:
            queryset = queryset.filter(municipality__iexact=municipality)
        if ward_number:
            queryset = queryset.filter(ward_number=ward_number)
        if classification:
            queryset = queryset.filter(land_use_classification=classification)
        if road_type:
            queryset = queryset.filter(road_type=road_type)
        if plot_shape:
            queryset = queryset.filter(plot_shape=plot_shape)
        for field, value in utility_filters.items():
            if value in ("true", "false"):
                queryset = queryset.filter(**{field: value == "true"})
        if furnishing:
            queryset = queryset.filter(furnishing_status=furnishing)
        if facing:
            queryset = queryset.filter(facing_direction=facing)
        if land_area_min is not None:
            try: queryset = queryset.filter(land_area_sqft__gte=convert_area(land_area_min, land_area_unit))
            except ValueError: raise ValidationError({"land_area_unit": "Unsupported area unit."})
        if land_area_max is not None:
            try: queryset = queryset.filter(land_area_sqft__lte=convert_area(land_area_max, land_area_unit))
            except ValueError: raise ValidationError({"land_area_unit": "Unsupported area unit."})
        if road_access_min is not None:
            queryset = queryset.filter(road_access_value__gte=road_access_min)
        if min_lat is not None: queryset = queryset.filter(latitude__gte=min_lat)
        if max_lat is not None: queryset = queryset.filter(latitude__lte=max_lat)
        if min_lng is not None: queryset = queryset.filter(longitude__gte=min_lng)
        if max_lng is not None: queryset = queryset.filter(longitude__lte=max_lng)

        if search:
            queryset = queryset.filter(
                Q(title__icontains=search)
                | Q(short_description__icontains=search)
                | Q(description__icontains=search)
                | Q(province__icontains=search)
                | Q(district__icontains=search)
                | Q(city__icontains=search)
                | Q(neighbourhood__icontains=search)
                | Q(municipality__icontains=search)
                | Q(tole__icontains=search)
                | Q(landmark__icontains=search)
                | Q(address__icontains=search)
            )

        ordering_fields = {
            "price": "price",
            "-price": "-price",
            "newest": "-created_at",
            "oldest": "created_at",
        }
        if ordering in ordering_fields:
            queryset = queryset.order_by(ordering_fields[ordering])

        return queryset


class PublicPropertyDetailView(generics.RetrieveAPIView):
    serializer_class = PublicPropertySerializer
    permission_classes = [AllowAny]
    authentication_classes = []

    def get_queryset(self):
        return get_public_properties_queryset(
            self.kwargs["license_number"]
        )


class PublicPropertyShareDetailView(generics.RetrieveAPIView):
    serializer_class = PublicPropertySerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    lookup_field = "share_slug"
    lookup_url_kwarg = "share_slug"

    def get_queryset(self):
        return Property.objects.filter(
            agency__slug=self.kwargs["slug"],
            agency__payment_status="paid",
            agency__is_active=True,
            is_published=True,
            status="available",
        ).select_related("agency", "assigned_agent").prefetch_related("media")


class PublicPropertyFilterOptionsView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = PublicPropertySerializer

    def get(self, request, license_number):
        properties = get_public_properties_queryset(
            license_number
        ).select_related(
            None
        ).prefetch_related(
            None
        ).order_by().values(
            "province",
            "district",
            "city",
            "neighbourhood",
            "municipality", "ward_number", "tole",
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

        for property_values in properties:
            add_location(property_values["province"], "province")
            add_location(property_values["district"], "district")
            add_location(property_values["city"], "city")
            add_location(property_values["neighbourhood"], "neighbourhood")
            add_location(property_values["municipality"], "municipality")
            add_location(property_values["tole"], "tole")

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
                "land_use_classifications": [{"value": value, "label": label} for value, label in Property.LAND_USE_CHOICES],
                "area_units": [{"value": value, "label": label} for value, label in Property.AREA_UNITS],
                "road_types": [{"value": value, "label": label} for value, label in Property.ROAD_TYPE_CHOICES],
                "plot_shapes": [{"value": value, "label": label} for value, label in Property.PLOT_SHAPE_CHOICES],
                "locations": location_values,
            }
        )
    
class PublicPropertyInquiryView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "public_submission"
    serializer_class = PublicPropertyInquirySerializer

    @transaction.atomic
    def post(self, request, license_number, property_id):
        serializer = PublicPropertyInquirySerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)

        property_obj = get_object_or_404(
            get_public_properties_queryset(license_number),
            id=property_id,
        )

        data = serializer.validated_data

        lead, lead_created = get_or_create_public_lead(
            agency=property_obj.agency,
            assigned_agent=property_obj.assigned_agent,
            full_name=data["full_name"],
            phone=data["phone"],
            email=data.get("email", ""),
            preferred_location=property_obj.city or property_obj.district,
            purpose=property_obj.purpose,
            property_type=property_obj.property_type,
            notes=data.get("message", ""),
        )

        lead_interest, _ = LeadPropertyInterest.objects.get_or_create(
            agency=property_obj.agency,
            lead=lead,
            property=property_obj,
            defaults={
                "interest_level": "high",
                "notes": data.get("message", ""),
            },
        )

        lead_interaction = LeadInteraction.objects.create(
            agency=property_obj.agency,
            lead=lead,
            agent=property_obj.assigned_agent,
            interaction_type="note",
            note=data.get("message", "Public property inquiry submitted."),
        )
        PropertyEvent.objects.create(
            agency=property_obj.agency,
            property=property_obj,
            lead=lead,
            event_type=PropertyEvent.EVENT_INQUIRY,
            visitor_id=request.headers.get("X-Visitor-ID", "")[:100],
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
                "lead_created": lead_created,
            },
            status=(status.HTTP_201_CREATED if lead_created else status.HTTP_200_OK),
        )
    
class PublicSimilarPropertiesView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = PublicPropertySerializer

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


class PublicPropertyEventView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "public_event"
    serializer_class = PublicPropertyEventSerializer

    def post(self, request, license_number, property_id):
        property_obj = get_object_or_404(
            get_public_properties_queryset(license_number),
            id=property_id,
        )
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        event = PropertyEvent.objects.create(
            agency=property_obj.agency,
            property=property_obj,
            **serializer.validated_data,
        )
        return Response(
            {"id": event.id, "event_type": event.event_type},
            status=status.HTTP_201_CREATED,
        )
