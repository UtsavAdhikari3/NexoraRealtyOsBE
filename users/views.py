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
)

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
                "message": "Agency registered successfully.",
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "full_name": user.full_name,
                    "role": user.role,
                },
                "agency": {
                    "id": user.agency.id,
                    "name": user.agency.name,
                    "license_number": user.agency.license_number,
                },
            },
            status=status.HTTP_201_CREATED,
        )
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

        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "message": "Login successful",

                "access": str(refresh.access_token),
                "refresh": str(refresh),

                "user": {
                    "id": user.id,
                    "email": user.email,
                    "full_name": user.full_name,
                    "role": user.role,
                },

                "agency": {
                    "id": user.agency.id if user.agency else None,
                    "name": user.agency.name if user.agency else None,
                    "license_number": (
                        user.agency.license_number
                        if user.agency
                        else None
                    ),
                },
            }
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