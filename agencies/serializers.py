from rest_framework import serializers


class TestMarkAgencyPaidSerializer(serializers.Serializer):
    email = serializers.EmailField()
    license_number = serializers.CharField(max_length=100)
    verify_email = serializers.BooleanField(default=True)