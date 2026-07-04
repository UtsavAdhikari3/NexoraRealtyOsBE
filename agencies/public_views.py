from rest_framework import generics
from rest_framework.permissions import AllowAny

from .models import Agency
from .public_serializers import PublicAgencySerializer


class PublicAgencyDetailView(generics.RetrieveAPIView):
    serializer_class = PublicAgencySerializer
    permission_classes = [AllowAny]
    lookup_field = "license_number"
    lookup_url_kwarg = "license_number"

    def get_queryset(self):
        return Agency.objects.filter(
            payment_status=Agency.PAYMENT_PAID
        )