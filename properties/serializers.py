from rest_framework import serializers

from .models import Property,PropertyMedia

class PropertyMediaSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyMedia
        fields = [
            "id",
            "media_type",
            "file",
            "thumbnail",
            "title",
            "caption",
            "sort_order",
            "is_primary",
            "created_at",
        ]


class PropertySerializer(serializers.ModelSerializer):
    media = PropertyMediaSerializer(many=True, read_only=True)

    class Meta:
        model = Property
        fields = "__all__"
        read_only_fields = ("agency",)