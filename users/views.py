from django.contrib.auth import authenticate, get_user_model

from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiExample
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import IsAuthenticated
from users.permissions import IsAgencyOwnerOrManager
from .serializers import (
    RegisterSerializer,
    LoginResponseSerializer,
    AgentSerializer,
    AgentCreateSerializer,
    VerifyLoginOTPSerializer,
    ResendLoginOTPSerializer,
)

from .models import EmailOTP
from .emails import send_login_verification_otp
from django.utils import timezone

User = get_user_model()

@extend_schema(
    summary="Register Agency",
    examples=[
        OpenApiExample(
            "Agency Registration",
            value={
                "full_name": "Sammy",
                "email": "sammy@nexora.com",
                "password": "Password123",
                "agency_name": "Nexora Realty",
                "license_number": "NR-001"
            },
            request_only=True,
        )
    ]
)
# users/views.py

class RegisterView(APIView):
    serializer_class = RegisterSerializer

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        return Response(
            {
                "message": "Agency registered successfully. Please complete payment before login.",
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "full_name": user.full_name,
                    "role": user.role,
                    "is_email_verified": user.is_email_verified,
                },
                "agency": {
                    "id": user.agency.id,
                    "name": user.agency.name,
                    "license_number": user.agency.license_number,
                    "payment_status": user.agency.payment_status,
                    "paid_at": user.agency.paid_at,
                },
            },
            status=status.HTTP_201_CREATED,
        )
    
def build_login_response(user):
    refresh = RefreshToken.for_user(user)

    if user.agency:
        agency_data = {
            "id": user.agency.id,
            "name": user.agency.name,
            "license_number": user.agency.license_number,
            "payment_status": user.agency.payment_status,
            "paid_at": user.agency.paid_at,
        }
    else:
        agency_data = None

    return {
        "message": "Login successful",

        "access": str(refresh.access_token),
        "refresh": str(refresh),

        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "is_email_verified": user.is_email_verified,
        },

        "agency": agency_data,
    }    
@extend_schema(
    summary="Login",
    request={
        "application/json": {
            "example": {
                "email": "sammy@nexora.com",
                "password": "Password123"
            }
        }
    },
    responses={
        200: LoginResponseSerializer
    }
)
class LoginView(APIView):
    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        user = authenticate(
            request,
            username=email,
            password=password
        )

        if not user:
            return Response(
                {
                    "detail": "Invalid email or password."
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if user.is_superuser or user.role == "super_admin":
            return Response(
                build_login_response(user)
            )

        if not user.agency:
            return Response(
                {
                    "detail": "This user is not linked to any agency."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if user.agency.payment_status != "paid":
            return Response(
                {
                    "detail": "Agency payment is not completed.",
                    "payment_required": True,
                    "payment_status": user.agency.payment_status,
                    "agency": {
                        "id": user.agency.id,
                        "name": user.agency.name,
                    },
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if not user.is_email_verified:
            send_login_verification_otp(user)

            return Response(
                {
                    "detail": "Email verification is required before login. OTP sent to your email.",
                    "otp_required": True,
                    "email": user.email,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(
            build_login_response(user)
        ) 
class AgentListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsAgencyOwnerOrManager]

    def get_queryset(self):
        return User.objects.filter(
            agency=self.request.user.agency,
            role="agent",
        ).order_by("-created_at")

    def get_serializer_class(self):
        if self.request.method == "POST":
            return AgentCreateSerializer

        return AgentSerializer


class AgentDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = AgentSerializer
    permission_classes = [IsAuthenticated, IsAgencyOwnerOrManager]

    def get_queryset(self):
        return User.objects.filter(
            agency=self.request.user.agency,
            role="agent",
        )

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active"])


class VerifyLoginOTPView(APIView):
    serializer_class = VerifyLoginOTPSerializer

    def post(self, request):
        serializer = VerifyLoginOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        otp = serializer.validated_data["otp"]

        user = User.objects.filter(
            email=email
        ).select_related(
            "agency"
        ).first()

        if not user:
            return Response(
                {
                    "detail": "Invalid OTP."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user.agency and not user.is_superuser:
            return Response(
                {
                    "detail": "This user is not linked to any agency."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if user.agency and user.agency.payment_status != "paid":
            return Response(
                {
                    "detail": "Agency payment is not completed.",
                    "payment_required": True,
                    "payment_status": user.agency.payment_status,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        otp_obj = EmailOTP.objects.filter(
            user=user,
            purpose=EmailOTP.PURPOSE_LOGIN_VERIFICATION,
            is_used=False,
        ).order_by(
            "-created_at"
        ).first()

        if not otp_obj:
            return Response(
                {
                    "detail": "Invalid or expired OTP."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if otp_obj.is_expired():
            otp_obj.is_used = True
            otp_obj.save(
                update_fields=[
                    "is_used"
                ]
            )

            return Response(
                {
                    "detail": "OTP has expired."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if otp_obj.attempts >= 5:
            otp_obj.is_used = True
            otp_obj.save(
                update_fields=[
                    "is_used"
                ]
            )

            return Response(
                {
                    "detail": "Too many incorrect OTP attempts. Please request a new OTP."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not otp_obj.check_code(otp):
            otp_obj.attempts += 1
            otp_obj.save(
                update_fields=[
                    "attempts"
                ]
            )

            return Response(
                {
                    "detail": "Invalid OTP."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        otp_obj.is_used = True
        otp_obj.save(
            update_fields=[
                "is_used"
            ]
        )

        user.is_email_verified = True
        user.save(
            update_fields=[
                "is_email_verified"
            ]
        )

        return Response(
            build_login_response(user)
        )
    

class ResendLoginOTPView(APIView):
    serializer_class = ResendLoginOTPSerializer

    def post(self, request):
        serializer = ResendLoginOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]

        user = authenticate(
            request,
            username=email,
            password=password
        )

        if not user:
            return Response(
                {
                    "detail": "Invalid email or password."
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if user.is_email_verified:
            return Response(
                {
                    "detail": "Email is already verified."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user.agency:
            return Response(
                {
                    "detail": "This user is not linked to any agency."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if user.agency.payment_status != "paid":
            return Response(
                {
                    "detail": "Agency payment is not completed.",
                    "payment_required": True,
                    "payment_status": user.agency.payment_status,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        send_login_verification_otp(user)

        return Response(
            {
                "message": "OTP resent to your email.",
                "otp_required": True,
                "email": user.email,
            },
            status=status.HTTP_200_OK,
        )