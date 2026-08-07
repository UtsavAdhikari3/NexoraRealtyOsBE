from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import Http404
from django.utils import timezone

from rest_framework import status
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .serializers import TestMarkAgencyPaidSerializer
from .serializers import AgencySerializer
from .models import Agency
from drf_spectacular.utils import extend_schema, inline_serializer

User = get_user_model()


class LocalizationView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses=inline_serializer(
            name="AgencyLocalizationSettings",
            fields={
                "language": serializers.ChoiceField(choices=["en", "ne"]),
                "date_system": serializers.ChoiceField(choices=["ad", "bs"]),
                "use_nepali_digits": serializers.BooleanField(),
                "timezone": serializers.CharField(),
                "now": serializers.JSONField(),
                "message_templates": serializers.JSONField(),
            },
        )
    )
    def get(self, request):
        from django.utils import timezone
        from .localization import (
            format_localized_date, resolved_message_templates,
        )

        agency = request.user.agency
        if not agency:
            return Response(
                {"detail": "An agency account is required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        now = timezone.now()
        return Response({
            "language": agency.default_language,
            "date_system": agency.default_date_system,
            "use_nepali_digits": agency.use_nepali_digits,
            "timezone": agency.timezone,
            "now": {
                "iso": now.isoformat(),
                "ad": format_localized_date(
                    now, date_system="ad", language=agency.default_language,
                    nepali_digits=agency.use_nepali_digits, include_time=True,
                ),
                "bs": format_localized_date(
                    now, date_system="bs", language=agency.default_language,
                    nepali_digits=agency.use_nepali_digits, include_time=True,
                ),
            },
            "message_templates": resolved_message_templates(agency.message_templates),
        })

    @extend_schema(
        request=inline_serializer(
            name="AgencyDateConversionRequest",
            fields={
                "date": serializers.CharField(),
                "source": serializers.ChoiceField(choices=["ad", "bs"]),
                "target": serializers.ChoiceField(choices=["ad", "bs"]),
                "language": serializers.ChoiceField(choices=["en", "ne"], required=False),
                "use_nepali_digits": serializers.BooleanField(required=False),
            },
        ),
        responses=inline_serializer(
            name="AgencyDateConversionResponse",
            fields={
                "source": serializers.CharField(),
                "target": serializers.CharField(),
                "date": serializers.CharField(),
                "display": serializers.CharField(),
            },
        ),
    )
    def post(self, request):
        from .localization import convert_date, format_localized_date

        value = request.data.get("date")
        source = request.data.get("source", "ad")
        target = request.data.get("target", "bs")
        if not value or source not in {"ad", "bs"} or target not in {"ad", "bs"} or source == target:
            return Response(
                {"detail": "Provide a date and different ad/bs source and target systems."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            nepali_digits = request.data.get("use_nepali_digits", False)
            if isinstance(nepali_digits, str):
                nepali_digits = nepali_digits.strip().lower() in {"1", "true", "yes", "on"}
            converted = convert_date(value, target=target)
            iso = f"{converted['year']:04d}-{converted['month']:02d}-{converted['day']:02d}"
            if target == "bs":
                display = format_localized_date(
                    value, date_system="bs",
                    language=request.data.get("language", "en"),
                    nepali_digits=bool(nepali_digits),
                )
            else:
                display = format_localized_date(
                    iso, date_system="ad",
                    language=request.data.get("language", "en"),
                    nepali_digits=bool(nepali_digits),
                )
        except (ValueError, TypeError, OverflowError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"source": source, "target": target, "date": iso, "display": display})


class CurrentAgencyView(APIView):
    serializer_class = AgencySerializer

    def get(self, request):
        if not request.user.is_authenticated or not request.user.agency_id:
            return Response(
                {"detail": "An agency account is required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(
            self.serializer_class(
                request.user.agency,
                context={"request": request},
            ).data
        )

    def patch(self, request):
        if not request.user.is_authenticated or not request.user.agency_id:
            return Response(
                {"detail": "An agency account is required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if request.user.role not in ["agency_owner", "agency_manager"]:
            return Response(
                {"detail": "Only owners or managers can update agency settings."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = self.serializer_class(
            request.user.agency,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class TestMarkAgencyPaidView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
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
