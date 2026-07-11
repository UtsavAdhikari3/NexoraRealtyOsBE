import requests

from rest_framework import generics, permissions
from rest_framework.exceptions import PermissionDenied

from .models import SocialPost
from .serializers import SocialPostSerializer
from django.conf import settings
from django.shortcuts import get_object_or_404, redirect
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import SocialAccount, SocialOAuthState
from .serializers import SocialAccountSerializer
from .services.meta import (
    build_meta_oauth_url,
    exchange_code_for_short_token,
    exchange_short_token_for_long_token,
    get_facebook_pages,
    get_instagram_account_from_page,
    MetaAPIError,
)
from .services.publishing import publish_social_post


class SocialPostListCreateView(generics.ListCreateAPIView):
    serializer_class = SocialPostSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        if user.role == "super_admin":
            return SocialPost.objects.select_related(
                "agency",
                "property",
                "created_by",
            )

        if not user.agency:
            return SocialPost.objects.none()

        return SocialPost.objects.filter(
            agency=user.agency
        ).select_related(
            "agency",
            "property",
            "created_by",
        )

    def perform_create(self, serializer):
        user = self.request.user

        if not user.agency:
            raise PermissionDenied("You must belong to an agency.")

        serializer.save(
            agency=user.agency,
            created_by=user,
        )


class SocialPostDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = SocialPostSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        if user.role == "super_admin":
            return SocialPost.objects.select_related(
                "agency",
                "property",
                "created_by",
            )

        if not user.agency:
            return SocialPost.objects.none()

        return SocialPost.objects.filter(
            agency=user.agency
        ).select_related(
            "agency",
            "property",
            "created_by",
        )


class SocialPostPublishView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "social_publish"
    serializer_class = SocialPostSerializer

    def post(self, request, pk):
        queryset = SocialPost.objects.select_related("social_account")
        if request.user.role != "super_admin":
            queryset = queryset.filter(agency=request.user.agency)
        post = get_object_or_404(queryset, pk=pk)
        account = post.social_account

        if not account:
            return Response(
                {"detail": "Select a connected social account first."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if account.status != SocialAccount.STATUS_CONNECTED:
            return Response(
                {"detail": "The selected social account is disconnected."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if account.platform != SocialAccount.PLATFORM_FACEBOOK:
            return Response(
                {"detail": "MVP direct publishing currently supports Facebook pages."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            publish_social_post(post)
            return Response(SocialPostSerializer(post).data)
        except Exception as exc:
            return Response(
                {"detail": "Publishing failed.", "error": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )
    
class MetaConnectionStartView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "oauth"
    serializer_class = SocialAccountSerializer

    def get(self, request):
        user = request.user

        if not user.agency:
            raise PermissionDenied("You must belong to an agency.")

        oauth_state = SocialOAuthState.create_state(
            provider=SocialAccount.PROVIDER_META,
            agency=user.agency,
            user=user,
        )

        auth_url = build_meta_oauth_url(oauth_state.state)

        return Response({
            "auth_url": auth_url,
        })


class MetaConnectionCallbackView(APIView):
    permission_classes = []
    authentication_classes = []
    throttle_scope = "oauth"
    serializer_class = SocialAccountSerializer

    def get(self, request):
        code = request.query_params.get("code")
        state = request.query_params.get("state")
        error = request.query_params.get("error")

        if error:
            return Response(
                {
                    "detail": "Meta connection was cancelled or failed.",
                    "error": error,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not code or not state:
            return Response(
                {"detail": "Missing code or state."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            oauth_state = SocialOAuthState.objects.select_related(
                "agency",
                "user",
            ).get(
                provider=SocialAccount.PROVIDER_META,
                state=state,
            )
        except SocialOAuthState.DoesNotExist:
            return Response(
                {"detail": "Invalid OAuth state."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not oauth_state.is_valid:
            return Response(
                {"detail": "OAuth state expired or already used."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            short_token_data = exchange_code_for_short_token(code)
            short_token = short_token_data.get("access_token")
            if not short_token:
                raise MetaAPIError("Meta did not return a short-lived access token.")

            long_token_data = exchange_short_token_for_long_token(short_token)
            long_token = long_token_data.get("access_token")
            if not long_token:
                raise MetaAPIError("Meta did not return a long-lived access token.")

            pages = get_facebook_pages(long_token)
        except MetaAPIError as exc:
            return Response(
                {
                    "detail": "Meta connection failed during token exchange.",
                    "meta_error": {
                        "message": str(exc),
                        "code": exc.code,
                        "type": exc.error_type,
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except requests.RequestException:
            return Response(
                {"detail": "Meta is temporarily unreachable. Please try again."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        connected_accounts = []

        for page in pages:
            page_id = page.get("id")
            page_name = page.get("name")
            page_access_token = page.get("access_token")

            if not page_id or not page_access_token:
                continue

            facebook_account, _ = SocialAccount.objects.update_or_create(
                agency=oauth_state.agency,
                provider=SocialAccount.PROVIDER_META,
                platform=SocialAccount.PLATFORM_FACEBOOK,
                external_id=page_id,
                defaults={
                    "name": page_name,
                    "username": None,
                    "page_id": page_id,
                    "access_token": page_access_token,
                    "status": SocialAccount.STATUS_CONNECTED,
                    "connected_by": oauth_state.user,
                },
            )

            connected_accounts.append(facebook_account)

            instagram_account_data = get_instagram_account_from_page(
                page_id=page_id,
                page_access_token=page_access_token,
            )

            if instagram_account_data:
                ig_id = instagram_account_data.get("id")
                ig_username = instagram_account_data.get("username")
                ig_name = instagram_account_data.get("name")

                instagram_account, _ = SocialAccount.objects.update_or_create(
                    agency=oauth_state.agency,
                    provider=SocialAccount.PROVIDER_META,
                    platform=SocialAccount.PLATFORM_INSTAGRAM,
                    external_id=ig_id,
                    defaults={
                        "name": ig_name or ig_username,
                        "username": ig_username,
                        "page_id": page_id,
                        "access_token": page_access_token,
                        "status": SocialAccount.STATUS_CONNECTED,
                        "connected_by": oauth_state.user,
                    },
                )

                connected_accounts.append(instagram_account)

        oauth_state.mark_used()

        serialized = SocialAccountSerializer(connected_accounts, many=True)

        return Response({
            "detail": "Meta connection completed.",
            "connected_accounts": serialized.data,
        })


class SocialAccountListView(generics.ListAPIView):
    serializer_class = SocialAccountSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        if user.role == "super_admin":
            return SocialAccount.objects.all()

        if not user.agency:
            return SocialAccount.objects.none()

        return SocialAccount.objects.filter(agency=user.agency)


class SocialAccountDisconnectView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SocialAccountSerializer

    def post(self, request, pk):
        user = request.user

        queryset = SocialAccount.objects.all()

        if user.role != "super_admin":
            queryset = queryset.filter(agency=user.agency)

        try:
            account = queryset.get(pk=pk)
        except SocialAccount.DoesNotExist:
            return Response(
                {"detail": "Social account not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        account.status = SocialAccount.STATUS_DISCONNECTED
        account.save(update_fields=["status"])

        return Response({
            "detail": "Social account disconnected.",
        })
