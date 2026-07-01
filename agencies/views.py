from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import Http404
from django.utils import timezone

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from .serializers import TestMarkAgencyPaidSerializer
from .models import Agency
from drf_spectacular.utils import extend_schema

User = get_user_model()


class TestMarkAgencyPaidView(APIView):
    permission_classes = [AllowAny]
    serializer_class = TestMarkAgencyPaidSerializer

    @extend_schema(
        request=TestMarkAgencyPaidSerializer,
        responses={
            200: TestMarkAgencyPaidSerializer,
        }
    )
    def post(self, request):
        if not settings.DEBUG:
            raise Http404()

        serializer = TestMarkAgencyPaidSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        license_number = serializer.validated_data["license_number"]
        verify_email = serializer.validated_data["verify_email"]

        user = User.objects.filter(
            email=email,
            agency__license_number=license_number
        ).select_related(
            "agency"
        ).first()

        if not user:
            return Response(
                {
                    "detail": "No user found for this email and license number."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        agency = user.agency

        agency.payment_status = Agency.PAYMENT_PAID
        agency.paid_at = timezone.now()
        agency.save(
            update_fields=[
                "payment_status",
                "paid_at",
            ]
        )

        if verify_email:
            user.is_email_verified = True
            user.save(
                update_fields=[
                    "is_email_verified",
                ]
            )

        return Response(
            {
                "message": "Test agency payment status updated.",
                "agency": {
                    "id": agency.id,
                    "name": agency.name,
                    "license_number": agency.license_number,
                    "payment_status": agency.payment_status,
                    "paid_at": agency.paid_at,
                },
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "role": user.role,
                    "is_email_verified": user.is_email_verified,
                },
            },
            status=status.HTTP_200_OK,
        )