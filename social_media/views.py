import requests
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions
from rest_framework.exceptions import PermissionDenied

from .models import SocialPost
from .serializers import SocialPostSerializer, SocialPublishRequestSerializer
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
    subscribe_page_to_webhooks,
    update_facebook_post,
    delete_facebook_post,
    delete_instagram_media,
    get_facebook_post_photo_id,
)
from .services.publishing import publish_social_post


def build_social_frontend_redirect_url(**result_params):
    """Add a non-sensitive OAuth result to the configured CRM return URL."""
    frontend_url = settings.FRONTEND_SOCIAL_SUCCESS_URL
    parts = urlsplit(frontend_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(
        {
            key: str(value)
            for key, value in result_params.items()
            if value is not None
        }
    )
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query),
            parts.fragment,
        )
    )


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

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(
            instance,
            data=request.data,
            partial=partial,
        )
        serializer.is_valid(raise_exception=True)

        published_results = instance.publish_results.filter(status="published")
        if "image" in serializer.validated_data and published_results.exists():
            return Response(
                {
                    "detail": (
                        "Published social-media images cannot be replaced. Create a "
                        "new post if you need to publish different media."
                    ),
                    "code": "published_media_is_immutable",
                },
                status=status.HTTP_409_CONFLICT,
            )

        next_caption = serializer.validated_data.get("caption", instance.caption)
        if next_caption != instance.caption:
            if published_results.filter(
                platform=SocialAccount.PLATFORM_INSTAGRAM
            ).exists():
                return Response(
                    {
                        "detail": (
                            "Instagram does not support editing the caption of "
                            "published media. The local post was left unchanged."
                        ),
                        "code": "instagram_caption_edit_unsupported",
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            facebook_results = instance.publish_results.select_related(
                "social_account"
            ).filter(
                platform=SocialAccount.PLATFORM_FACEBOOK,
                status="published",
            )
            for publish_result in facebook_results:
                if not publish_result.external_post_id:
                    return Response(
                        {
                            "detail": (
                                "The published Facebook post ID is missing, so the "
                                "caption was not changed locally."
                            )
                        },
                        status=status.HTTP_409_CONFLICT,
                    )
                try:
                    update_facebook_post(
                        post_id=publish_result.external_post_id,
                        page_access_token=publish_result.social_account.access_token,
                        message=next_caption,
                    )
                except MetaAPIError as exc:
                    return Response(
                        {
                            "detail": (
                                "Facebook rejected the post update. The local post "
                                "was left unchanged."
                            ),
                            "meta_error": {
                                "message": str(exc),
                                "code": exc.code,
                                "type": exc.error_type,
                            },
                        },
                        status=status.HTTP_502_BAD_GATEWAY,
                    )
                except requests.RequestException:
                    return Response(
                        {
                            "detail": (
                                "Facebook is temporarily unreachable. The local post "
                                "was left unchanged."
                            )
                        },
                        status=status.HTTP_502_BAD_GATEWAY,
                    )

        self.perform_update(serializer)
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instagram_results = instance.publish_results.select_related(
            "social_account"
        ).filter(
            platform=SocialAccount.PLATFORM_INSTAGRAM,
            status="published",
        )

        for publish_result in instagram_results:
            media_id = (
                publish_result.external_media_id
                or publish_result.external_post_id
            )
            if not media_id:
                return Response(
                    {
                        "detail": (
                            "The published Instagram media ID is missing, so the post "
                            "was not deleted locally."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            management_token = publish_result.social_account.user_access_token
            if not management_token:
                return Response(
                    {
                        "detail": (
                            "Reconnect Meta before deleting this Instagram post. "
                            "Nexora needs the instagram_manage_contents permission."
                        ),
                        "code": "instagram_reconnect_required",
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            try:
                delete_instagram_media(
                    media_id=media_id,
                    user_access_token=management_token,
                )
            except MetaAPIError as exc:
                return Response(
                    {
                        "detail": (
                            "Instagram rejected the media deletion. The local post "
                            "was left unchanged."
                        ),
                        "meta_error": {
                            "message": str(exc),
                            "code": exc.code,
                            "type": exc.error_type,
                        },
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )
            except requests.RequestException:
                return Response(
                    {
                        "detail": (
                            "Instagram is temporarily unreachable. The local post was "
                            "left unchanged."
                        )
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )

        facebook_results = instance.publish_results.select_related(
            "social_account"
        ).filter(
            platform=SocialAccount.PLATFORM_FACEBOOK,
            status="published",
        )

        for publish_result in facebook_results:
            if not publish_result.external_post_id:
                return Response(
                    {
                        "detail": (
                            "The published Facebook post ID is missing, so the post "
                            "was not deleted locally."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            try:
                delete_target_id = publish_result.external_media_id
                if instance.image and not delete_target_id:
                    delete_target_id = get_facebook_post_photo_id(
                        post_id=publish_result.external_post_id,
                        page_access_token=publish_result.social_account.access_token,
                    )
                if not delete_target_id:
                    delete_target_id = publish_result.external_post_id
                delete_facebook_post(
                    post_id=delete_target_id,
                    page_access_token=publish_result.social_account.access_token,
                )
            except MetaAPIError as exc:
                return Response(
                    {
                        "detail": (
                            "Facebook rejected the post deletion. The local post was "
                            "left unchanged."
                        ),
                        "meta_error": {
                            "message": str(exc),
                            "code": exc.code,
                            "type": exc.error_type,
                        },
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )
            except requests.RequestException:
                return Response(
                    {
                        "detail": (
                            "Facebook is temporarily unreachable. The local post was "
                            "left unchanged."
                        )
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )

        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SocialPostPublishView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "social_publish"
    serializer_class = SocialPostSerializer

    @extend_schema(request=SocialPublishRequestSerializer, responses=SocialPostSerializer)
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
        request_serializer = SocialPublishRequestSerializer(data=request.data or {})
        request_serializer.is_valid(raise_exception=True)
        platforms = request_serializer.validated_data.get("platforms")

        publish_social_post(post, platforms=platforms)
        post.refresh_from_db()
        response_status = status.HTTP_200_OK
        if post.status == SocialPost.STATUS_PARTIAL:
            response_status = status.HTTP_207_MULTI_STATUS
        elif post.status == SocialPost.STATUS_FAILED:
            response_status = status.HTTP_502_BAD_GATEWAY

        return Response(
            SocialPostSerializer(post, context={"request": request}).data,
            status=response_status,
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
        connection_warnings = []

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
                    "user_access_token": long_token,
                    "status": SocialAccount.STATUS_CONNECTED,
                    "connected_by": oauth_state.user,
                },
            )

            connected_accounts.append(facebook_account)

            try:
                subscribe_page_to_webhooks(
                    page_id=page_id,
                    page_access_token=page_access_token,
                )
                facebook_account.webhook_subscription_status = "subscribed"
                facebook_account.webhook_subscribed_at = timezone.now()
                facebook_account.webhook_error = ""
                facebook_account.save(
                    update_fields=[
                        "webhook_subscription_status",
                        "webhook_subscribed_at",
                        "webhook_error",
                    ]
                )
            except MetaAPIError as exc:
                facebook_account.webhook_subscription_status = "failed"
                facebook_account.webhook_error = str(exc)
                facebook_account.save(
                    update_fields=[
                        "webhook_subscription_status",
                        "webhook_error",
                    ]
                )
                connection_warnings.append(
                    {
                        "page_id": page_id,
                        "capability": "messaging_webhooks",
                        "message": str(exc),
                        "code": exc.code,
                    }
                )

            try:
                instagram_account_data = get_instagram_account_from_page(
                    page_id=page_id,
                    page_access_token=page_access_token,
                )
            except MetaAPIError as exc:
                instagram_account_data = None
                connection_warnings.append(
                    {
                        "page_id": page_id,
                        "message": str(exc),
                        "code": exc.code,
                    }
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
                        "user_access_token": long_token,
                        "status": SocialAccount.STATUS_CONNECTED,
                        "connected_by": oauth_state.user,
                        "webhook_subscription_status": (
                            facebook_account.webhook_subscription_status
                        ),
                        "webhook_subscribed_at": facebook_account.webhook_subscribed_at,
                        "webhook_error": facebook_account.webhook_error,
                    },
                )

                connected_accounts.append(instagram_account)

        oauth_state.mark_used()

        return redirect(
            build_social_frontend_redirect_url(
                meta_connection="success",
                connected_count=len(connected_accounts),
                warning_count=len(connection_warnings),
            )
        )


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

    def delete(self, request, pk):
        return self.post(request, pk)
