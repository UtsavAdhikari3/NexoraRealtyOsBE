from django.db.models import Case, Count, F, IntegerField, Prefetch, Q, Value, When
from django.shortcuts import redirect
from django.utils import timezone
from decimal import Decimal, InvalidOperation

from rest_framework import generics
from rest_framework.pagination import PageNumberPagination
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

from .models import Property, PropertyDistributionLink, PropertyEvent, PropertyMedia
from agencies.public_selectors import get_public_agency
from agencies.website_urls import add_url_query
from .area import convert_area
from .public_selectors import public_properties
from .public_serializers import (
    PublicPropertyEventSerializer,
    PublicPropertyCardSerializer,
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
from urllib.parse import urlencode


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


class PublicPropertyPagination(PageNumberPagination):
    page_size = 24
    page_size_query_param = "page_size"
    max_page_size = 60


def public_media_queryset():
    return PropertyMedia.objects.filter(
        is_public=True,
        media_type__in=["image", "video", "reel"],
    ).order_by("-is_primary", "sort_order", "created_at")


class PublicDistributionLinkRedirectView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, code):
        from .distribution import canonical_property_url

        link = get_object_or_404(
            PropertyDistributionLink.objects.select_related("property__agency"),
            code=code,
            is_active=True,
            agency__is_active=True,
        )
        property_obj = get_object_or_404(
            public_properties(),
            pk=link.property_id,
            agency_id=link.agency_id,
        )
        now = timezone.now()
        PropertyDistributionLink.objects.filter(pk=link.pk).update(
            click_count=F("click_count") + 1,
            last_clicked_at=now,
        )
        PropertyEvent.objects.create(
            agency=link.agency,
            property=link.property,
            event_type=PropertyEvent.EVENT_DISTRIBUTION_CLICK,
            visitor_id=request.headers.get("X-Visitor-ID", "")[:100],
            referrer=request.headers.get("Referer", "")[:1000],
            utm_source=link.source,
            utm_medium=link.medium,
            utm_campaign=link.campaign,
            metadata={"distribution_code": link.code, "label": link.label},
        )
        query = {
            "utm_source": link.source,
            "utm_medium": link.medium,
            "utm_campaign": link.campaign,
            "nexora_link": link.code,
        }
        return redirect(add_url_query(canonical_property_url(property_obj), query))


def get_public_properties_queryset(license_number):
    agency = get_public_agency(license_number=license_number)
    return public_properties(agency=agency).select_related(
        "agency",
        "assigned_agent",
        "verification",
    ).prefetch_related(
        Prefetch(
            "media",
            queryset=public_media_queryset(),
            to_attr="_ordered_public_media",
        ),
        "verification__documents",
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
    serializer_class = PublicPropertyCardSerializer
    pagination_class = PublicPropertyPagination
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
        assigned_agent = self.request.query_params.get("assigned_agent")
        ids_value = self.request.query_params.get("ids")
        min_lat = self.request.query_params.get("min_lat")
        max_lat = self.request.query_params.get("max_lat")
        min_lng = self.request.query_params.get("min_lng")
        max_lng = self.request.query_params.get("max_lng")

        if property_type and property_type != "all":
            queryset = queryset.filter(property_type=property_type)

        if purpose and purpose != "all":
            queryset = queryset.filter(purpose=purpose)

        if assigned_agent not in (None, "", "all"):
            if not str(assigned_agent).isdigit():
                raise ValidationError({"assigned_agent": "Enter a valid agent ID."})
            from users.models import AgencyUser
            agent_id = int(assigned_agent)
            if not AgencyUser.objects.filter(
                pk=agent_id,
                agency__license_number=self.kwargs["license_number"],
                role=AgencyUser.ROLE_AGENT,
                is_active=True,
            ).exists():
                raise ValidationError({"assigned_agent": "Choose an active agent from this agency."})
            queryset = queryset.filter(assigned_agent_id=agent_id)

        requested_ids = []
        if ids_value:
            raw_ids = [item.strip() for item in ids_value.split(",") if item.strip()]
            if len(raw_ids) > 24 or any(not item.isdigit() for item in raw_ids):
                raise ValidationError({"ids": "Provide at most 24 comma-separated property IDs."})
            requested_ids = list(dict.fromkeys(int(item) for item in raw_ids))
            queryset = queryset.filter(id__in=requested_ids)

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
            "latest": ("-published_at", "-created_at"),
            "featured": ("-is_featured", "-published_at", "-created_at"),
            "price_asc": ("price", "id"),
            "price_desc": ("-price", "id"),
            "oldest": ("published_at", "created_at"),
            # Backwards-compatible aliases.
            "price": ("price", "id"),
            "-price": ("-price", "id"),
            "newest": ("-published_at", "-created_at"),
        }
        if ordering in ordering_fields:
            queryset = queryset.order_by(*ordering_fields[ordering])
        elif requested_ids:
            requested_order = Case(
                *[When(id=value, then=position) for position, value in enumerate(requested_ids)],
                output_field=IntegerField(),
            )
            queryset = queryset.order_by(requested_order)

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
        agency = get_public_agency(slug=self.kwargs["slug"])
        return public_properties(agency=agency).select_related(
            "agency", "assigned_agent", "verification"
        ).prefetch_related(
            Prefetch("media", queryset=public_media_queryset(), to_attr="_ordered_public_media"),
            "verification__documents",
        )


class PublicPropertyFilterOptionsView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = PublicPropertySerializer

    def get(self, request, license_number):
        properties = get_public_properties_queryset(license_number).select_related(
            None
        ).prefetch_related(None).order_by()

        def counted(field, labels=None):
            grouped = properties.exclude(**{field: ""}).values(field).annotate(
                count=Count("id")
            ).order_by(field)
            merged = {}
            for item in grouped:
                raw = str(item[field] or "").strip()
                if not raw:
                    continue
                key = raw.casefold()
                if key not in merged:
                    merged[key] = {"value": raw, "label": (labels or {}).get(raw, raw), "count": 0}
                merged[key]["count"] += item["count"]
            return sorted(merged.values(), key=lambda item: item["label"].casefold())

        purpose_counts = {item["purpose"]: item["count"] for item in properties.values("purpose").annotate(count=Count("id"))}
        property_type_labels = dict(Property.PROPERTY_TYPES)
        purpose_labels = dict(Property.PURPOSES)
        from users.models import AgencyUser
        agency = get_public_agency(license_number=license_number)

        return Response(
            {
                "summary": {
                    "total": properties.count(),
                    "sale": purpose_counts.get("sale", 0),
                    "rent": purpose_counts.get("rent", 0),
                    "lease": purpose_counts.get("lease", 0),
                    "featured": properties.filter(is_featured=True).count(),
                    "agents": AgencyUser.objects.filter(
                        agency=agency, role=AgencyUser.ROLE_AGENT, is_active=True
                    ).count(),
                },
                "property_types": counted("property_type", property_type_labels),
                "purposes": counted("purpose", purpose_labels),
                "land_use_classifications": [{"value": value, "label": label} for value, label in Property.LAND_USE_CHOICES],
                "area_units": [{"value": value, "label": label} for value, label in Property.AREA_UNITS],
                "road_types": [{"value": value, "label": label} for value, label in Property.ROAD_TYPE_CHOICES],
                "plot_shapes": [{"value": value, "label": label} for value, label in Property.PLOT_SHAPE_CHOICES],
                "locations": {
                    "provinces": counted("province"),
                    "districts": counted("district"),
                    "cities": counted("city"),
                    "municipalities": counted("municipality"),
                    "neighbourhoods": counted("neighbourhood"),
                    "toles": counted("tole"),
                },
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
            full_name=data["full_name"],
            phone=data["phone"],
            email=data.get("email", ""),
            preferred_location=property_obj.city or property_obj.district,
            purpose=property_obj.purpose,
            property_type=property_obj.property_type,
            notes=data.get("message", ""),
            property_obj=property_obj,
        )
        attribution = {
            key: data.get(key, "")
            for key in ("utm_source", "utm_medium", "utm_campaign", "distribution_code")
            if data.get(key)
        }
        if attribution:
            lead.custom_data = {**(lead.custom_data or {}), "distribution_attribution": attribution}
            lead.save(update_fields=["custom_data", "updated_at"])

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
            agent=lead.assigned_agent,
            interaction_type="note",
            direction="inbound",
            note=data.get("message", "Public property inquiry submitted."),
        )
        PropertyEvent.objects.create(
            agency=property_obj.agency,
            property=property_obj,
            lead=lead,
            event_type=PropertyEvent.EVENT_INQUIRY,
            visitor_id=request.headers.get("X-Visitor-ID", "")[:100],
            utm_source=data.get("utm_source", ""),
            utm_medium=data.get("utm_medium", ""),
            utm_campaign=data.get("utm_campaign", ""),
            metadata={"distribution_code": data.get("distribution_code", "")},
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
    serializer_class = PublicPropertyCardSerializer

    def get(self, request, license_number, property_id):
        current_property = get_object_or_404(
            get_public_properties_queryset(license_number),
            id=property_id,
        )

        candidates = get_public_properties_queryset(license_number).exclude(id=current_property.id)

        score = Case(
            When(purpose=current_property.purpose, then=Value(40)),
            default=Value(0), output_field=IntegerField(),
        ) + Case(
            When(property_type=current_property.property_type, then=Value(30)),
            default=Value(0), output_field=IntegerField(),
        )
        if current_property.municipality:
            score += Case(When(municipality__iexact=current_property.municipality, then=Value(20)), default=Value(0), output_field=IntegerField())
        if current_property.city:
            score += Case(When(city__iexact=current_property.city, then=Value(15)), default=Value(0), output_field=IntegerField())
        if current_property.district:
            score += Case(When(district__iexact=current_property.district, then=Value(10)), default=Value(0), output_field=IntegerField())
        if current_property.price:
            score += Case(
                When(price__gte=current_property.price * Decimal("0.75"), price__lte=current_property.price * Decimal("1.25"), then=Value(15)),
                When(price__gte=current_property.price * Decimal("0.50"), price__lte=current_property.price * Decimal("1.50"), then=Value(8)),
                default=Value(0), output_field=IntegerField(),
            )
        if current_property.property_type != "land" and current_property.bedrooms:
            score += Case(
                When(bedrooms__gte=max(0, current_property.bedrooms - 1), bedrooms__lte=current_property.bedrooms + 1, then=Value(8)),
                default=Value(0), output_field=IntegerField(),
            )
        if current_property.property_type == "land" and current_property.land_area_sqft:
            score += Case(
                When(
                    land_area_sqft__gte=current_property.land_area_sqft * Decimal("0.67"),
                    land_area_sqft__lte=current_property.land_area_sqft * Decimal("1.50"),
                    then=Value(8),
                ),
                default=Value(0), output_field=IntegerField(),
            )
        score += Case(When(is_featured=True, then=Value(2)), default=Value(0), output_field=IntegerField())
        similar_properties = candidates.annotate(similarity_score=score).order_by(
            "-similarity_score", "-published_at", "-created_at"
        )[:6]

        serializer = PublicPropertyCardSerializer(
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
