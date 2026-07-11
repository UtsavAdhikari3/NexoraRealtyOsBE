from django.db import connection
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import serializers


class HealthCheckSerializer(serializers.Serializer):
    status = serializers.CharField()
    database = serializers.CharField()


class HealthCheckView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = HealthCheckSerializer

    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception:
            return Response({"status": "unhealthy", "database": "unavailable"}, status=503)

        return Response({"status": "healthy", "database": "available"})
