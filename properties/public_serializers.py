from rest_framework import serializers

from .models import Property, PropertyMedia


class PublicPropertyMediaSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyMedia
        fields = [
            "id",
            "media_type",
            "file",
            "external_url",
            "thumbnail",
            "title",
            "caption",
            "sort_order",
            "is_primary",
            "created_at",
        ]


class PublicPropertySerializer(serializers.ModelSerializer):
    media = PublicPropertyMediaSerializer(
        many=True,
        read_only=True
    )

    agency_name = serializers.SerializerMethodField()
    assigned_agent_name = serializers.SerializerMethodField()
    location_display = serializers.SerializerMethodField()

    class Meta:
        model = Property
        fields = [
            "id",
            "title",
            "property_type",
            "purpose",
            "price",
            "currency",

            "province",
            "district",
            "city",
            "neighbourhood",
            "address",
            "latitude",
            "longitude",
            "location_display",

            "bedrooms",
            "bathrooms",
            "floors",

            "land_area_value",
            "land_area_unit",
            "built_up_area_value",
            "built_up_area_unit",
            "road_access_value",
            "road_access_unit",

            "amenities",
            "virtual_tour_url",
            "short_description",
            "description",

            "is_featured",
            "published_at",

            "agency_name",
            "assigned_agent_name",

            "media",
            "created_at",
            "updated_at",
        ]

    def get_agency_name(self, obj):
        if obj.agency:
            return obj.agency.name

        return None

    def get_assigned_agent_name(self, obj):
        if obj.assigned_agent:
            return obj.assigned_agent.full_name

        return None

    def get_location_display(self, obj):
        parts = [
            obj.neighbourhood,
            obj.city,
            obj.district,
            obj.province,
        ]

        return ", ".join(
            [
                part
                for part in parts
                if part
            ]
        )