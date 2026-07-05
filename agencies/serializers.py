from rest_framework import serializers
from .models import Agency

class TestMarkAgencyPaidSerializer(serializers.Serializer):
    email = serializers.EmailField()
    license_number = serializers.CharField(max_length=100)
    verify_email = serializers.BooleanField(default=True)

class AgencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Agency
        fields = "__all__"