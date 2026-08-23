import requests
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.utils import timezone
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions
from rest_framework.exceptions import PermissionDenied
from rest_framework.throttling import ScopedRateThrottle

from .models import SocialPost
from .serializers import SocialPostSerializer, SocialPublishRequestSerializer
from django.conf import settings
from django.shortcuts import get_object_or_404, redirect
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import SocialAccount, SocialConnectionSession, SocialOAuthState
from .serializers import (
    MetaPageSelectionSerializer,
    SocialAccountSerializer,
    SocialConnectionSessionSerializer,
    WhatsAppConnectionCompleteSerializer,
)
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
    exchange_whatsapp_signup_code,
    get_whatsapp_phone_numbers,
    subscribe_whatsapp_business_account,
)
from .services.publishing import publish_social_post
from users.models import AgencyUser


SOCIAL_CONNECTION_MANAGER_ROLES = {
    AgencyUser.ROLE_AGENCY_OWNER,
    AgencyUser.ROLE_AGENCY_MANAGER,
}


def require_social_connection_manager(user):
    if user.role not in SOCIAL_CONNECTION_MANAGER_ROLES:
        raise PermissionDenied(
            "Only an agency owner or manager can manage social connections."
        )
    if not user.agency_id:
        raise PermissionDenied("You must belong to an agency.")


def connect_selected_meta_pages(*, session, selected_page_ids):
    pages_by_id = {
        str(page.get("id")): page
        for page in session.candidate_pages
        if page.get("id")
    }
    selected_pages = [pages_by_id[page_id] for page_id in selected_page_ids]
    connected_accounts = []
    connection_warnings = []

    for page in selected_pages:
        page_id = str(page["id"])
        page_name = page.get("name")
        page_access_token = page.get("access_token")
        if not page_access_token:
            connection_warnings.append(
                {
                    "page_id": page_id,
                    "capability": "page_connection",
                    "message": "Meta did not return an access token for this Page.",
                }
            )
            continue

        facebook_account, _ = SocialAccount.objects.update_or_create(
            agency=session.agency,
            provider=SocialAccount.PROVIDER_META,
            platform=SocialAccount.PLATFORM_FACEBOOK,
            external_id=page_id,
            defaults={
                "name": page_name,
                "username": None,
                "page_id": page_id,
                "access_token": page_access_token,
                "user_access_token": session.user_access_token,
                "status": SocialAccount.STATUS_CONNECTED,
                "connected_by": session.user,
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
        except MetaAPIError as exc:
            facebook_account.webhook_subscription_status = "failed"
            facebook_account.webhook_error = str(exc)
            connection_warnings.append(
                {
                    "page_id": page_id,
                    "capability": "messaging_webhooks",
                    "message": str(exc),
                    "code": exc.code,
                }
            )
        facebook_account.save(
            update_fields=[
                "webhook_subscription_status",
                "webhook_subscribed_at",
                "webhook_error",
            ]
        )

        instagram_account_data = page.get("instagram_business_account")
        if not instagram_account_data or not instagram_account_data.get("username"):
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
                        "capability": "instagram_discovery",
                        "message": str(exc),
                        "code": exc.code,
                    }
                )

        if not instagram_account_data:
            continue

        ig_id = instagram_account_data.get("id")
        if not ig_id:
            continue
        ig_username = instagram_account_data.get("username")
        ig_name = instagram_account_data.get("name")
        instagram_account, _ = SocialAccount.objects.update_or_create(
            agency=session.agency,
            provider=SocialAccount.PROVIDER_META,
            platform=SocialAccount.PLATFORM_INSTAGRAM,
            external_id=ig_id,
            defaults={
                "name": ig_name or ig_username,
                "username": ig_username,
                "page_id": page_id,
                "access_token": page_access_token,
                "user_access_token": session.user_access_token,
                "status": SocialAccount.STATUS_CONNECTED,
                "connected_by": session.user,
                "webhook_subscription_status": (
                    facebook_account.webhook_subscription_status
                ),
                "webhook_subscribed_at": facebook_account.webhook_subscribed_at,
                "webhook_error": facebook_account.webhook_error,
            },
        )
        connected_accounts.append(instagram_account)

    return connected_accounts, connection_warnings


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
    throttle_scope = "social_upload"

    def get_throttles(self):
        if self.request.method == "POST":
            return [ScopedRateThrottle()]
        return []

    def get_queryset(self):
        user = self.request.user

        if user.role == "super_admin":
            return SocialPost.objects.select_related(
                "agency",
                "property",
                "created_by",
            ).prefetch_related("media_items")

        if not user.agency:
            return SocialPost.objects.none()

        return SocialPost.objects.filter(
            agency=user.agency
        ).select_related(
            "agency",
            "property",
            "created_by",
        ).prefetch_related("media_items")

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
            ).prefetch_related("media_items")

        if not user.agency:
            return SocialPost.objects.none()

        return SocialPost.objects.filter(
            agency=user.agency
        ).select_related(
            "agency",
            "property",
            "created_by",
        ).prefetch_related("media_items")

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
        if serializer.media_changed and published_results.exists():
            return Response(
                {
                    "detail": (
                        "Published social-media files cannot be replaced. Create a "
                        "new post if you need to publish different media."
                    ),
                    "code": "published_media_is_immutable",
                },
                status=status.HTTP_409_CONFLICT,
            )

        next_caption = serializer.validated_data.get("caption", instance.caption)
        if next_caption != instance.caption:
            if instance.post_format == SocialPost.FORMAT_REEL and published_results.exists():
                return Response(
                    {
                        "detail": (
                            "Published Reel captions cannot be edited reliably on both "
                            "Meta platforms. Create a new Reel instead."
                        ),
                        "code": "published_reel_caption_edit_unsupported",
                    },
                    status=status.HTTP_409_CONFLICT,
                )
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
                media_count = instance.media_items.count()
                if media_count > 1:
                    delete_target_id = publish_result.external_post_id
                else:
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

        video_name = instance.video.name if instance.video else ""
        video_storage = instance.video.storage if instance.video else None
        self.perform_destroy(instance)
        if video_name and video_storage:
            transaction.on_commit(lambda: video_storage.delete(video_name))
        return Response(status=status.HTTP_204_NO_CONTENT)


class SocialPostPublishView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "social_publish"
    serializer_class = SocialPostSerializer

    @extend_schema(request=SocialPublishRequestSerializer, responses=SocialPostSerializer)
    def post(self, request, pk):
        queryset = SocialPost.objects.select_related("social_account").prefetch_related(
            "media_items"
        )
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
        require_social_connection_manager(user)

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
            return redirect(
                build_social_frontend_redirect_url(
                    meta_connection="error",
                    error_code=error,
                )
            )

        if not code or not state:
            return redirect(
                build_social_frontend_redirect_url(
                    meta_connection="error",
                    error_code="missing_code_or_state",
                )
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
            return redirect(
                build_social_frontend_redirect_url(
                    meta_connection="error",
                    error_code="invalid_state",
                )
            )

        if not oauth_state.is_valid:
            return redirect(
                build_social_frontend_redirect_url(
                    meta_connection="error",
                    error_code="expired_state",
                )
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
            return redirect(
                build_social_frontend_redirect_url(
                    meta_connection="error",
                    error_code=exc.code or "token_exchange_failed",
                )
            )
        except requests.RequestException:
            return redirect(
                build_social_frontend_redirect_url(
                    meta_connection="error",
                    error_code="meta_unreachable",
                )
            )

        if not pages:
            oauth_state.mark_used()
            return redirect(
                build_social_frontend_redirect_url(
                    meta_connection="error",
                    error_code="no_pages",
                )
            )

        connection_session = SocialConnectionSession.create_session(
            agency=oauth_state.agency,
            user=oauth_state.user,
            pages=pages,
            user_access_token=long_token,
        )
        oauth_state.mark_used()

        return redirect(
            build_social_frontend_redirect_url(
                meta_connection="select",
                connection_session=connection_session.token,
                page_count=len(pages),
            )
        )


class MetaConnectionSessionView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "oauth"

    def get_session(self, request, token):
        require_social_connection_manager(request.user)
        session = get_object_or_404(
            SocialConnectionSession.objects.select_related("agency", "user"),
            token=token,
            agency=request.user.agency,
            user=request.user,
        )
        if not session.is_valid:
            return None
        return session

    @extend_schema(responses=SocialConnectionSessionSerializer)
    def get(self, request, token):
        session = self.get_session(request, token)
        if session is None:
            return Response(
                {"detail": "This Page-selection session expired or was completed."},
                status=status.HTTP_410_GONE,
            )
        return Response(SocialConnectionSessionSerializer(session).data)

    @extend_schema(
        request=MetaPageSelectionSerializer,
        responses=SocialAccountSerializer(many=True),
    )
    def post(self, request, token):
        session = self.get_session(request, token)
        if session is None:
            return Response(
                {"detail": "This Page-selection session expired or was completed."},
                status=status.HTTP_410_GONE,
            )
        serializer = MetaPageSelectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        page_ids = serializer.validated_data["page_ids"]
        available_ids = {
            str(page.get("id"))
            for page in session.candidate_pages
            if page.get("id")
        }
        unknown = [page_id for page_id in page_ids if page_id not in available_ids]
        if unknown:
            return Response(
                {"page_ids": ["One or more selected Pages are unavailable."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        accounts, warnings = connect_selected_meta_pages(
            session=session,
            selected_page_ids=page_ids,
        )
        session.complete()
        return Response(
            {
                "accounts": SocialAccountSerializer(accounts, many=True).data,
                "connected_count": len(accounts),
                "warning_count": len(warnings),
                "warnings": warnings,
            }
        )


class WhatsAppConnectionStartView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "oauth"

    def get(self, request):
        require_social_connection_manager(request.user)
        if not settings.META_APP_ID or not settings.META_WHATSAPP_LOGIN_CONFIG_ID:
            return Response(
                {
                    "detail": (
                        "WhatsApp Embedded Signup is not configured. Set "
                        "META_APP_ID and META_WHATSAPP_LOGIN_CONFIG_ID."
                    )
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        oauth_state = SocialOAuthState.create_state(
            provider="whatsapp",
            agency=request.user.agency,
            user=request.user,
        )
        return Response(
            {
                "app_id": settings.META_APP_ID,
                "config_id": settings.META_WHATSAPP_LOGIN_CONFIG_ID,
                "state": oauth_state.state,
                "graph_version": settings.META_GRAPH_VERSION,
            }
        )


class WhatsAppConnectionCompleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "oauth"
    serializer_class = WhatsAppConnectionCompleteSerializer

    @transaction.atomic
    def post(self, request):
        require_social_connection_manager(request.user)
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data

        try:
            oauth_state = SocialOAuthState.objects.select_for_update().get(
                provider="whatsapp",
                state=values["state"],
                agency=request.user.agency,
                user=request.user,
            )
        except SocialOAuthState.DoesNotExist:
            return Response(
                {"detail": "This WhatsApp connection session is invalid."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not oauth_state.is_valid:
            return Response(
                {"detail": "This WhatsApp connection session expired or was used."},
                status=status.HTTP_410_GONE,
            )

        try:
            token_data = exchange_whatsapp_signup_code(values["code"])
            access_token = token_data.get("access_token")
            if not access_token:
                raise MetaAPIError("Meta did not return a WhatsApp access token.")
            phone_numbers = get_whatsapp_phone_numbers(
                values["business_account_id"],
                access_token,
            )
            phone = next(
                (
                    item
                    for item in phone_numbers
                    if str(item.get("id")) == values["phone_number_id"]
                ),
                None,
            )
            if phone is None:
                return Response(
                    {
                        "detail": (
                            "The selected phone number does not belong to the "
                            "authorized WhatsApp Business account."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if SocialAccount.objects.filter(
                provider=SocialAccount.PROVIDER_META,
                platform=SocialAccount.PLATFORM_WHATSAPP,
                external_id=values["phone_number_id"],
                status=SocialAccount.STATUS_CONNECTED,
            ).exclude(agency=request.user.agency).exists():
                return Response(
                    {
                        "detail": (
                            "This WhatsApp phone number is already connected to "
                            "another Nexora agency."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            subscribe_whatsapp_business_account(
                values["business_account_id"],
                access_token,
            )
        except MetaAPIError as exc:
            return Response(
                {
                    "detail": str(exc),
                    "code": exc.code or "whatsapp_connection_failed",
                },
                status=exc.status_code or status.HTTP_502_BAD_GATEWAY,
            )
        except requests.RequestException:
            return Response(
                {"detail": "Meta could not be reached. Please try again."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        token_expires_at = None
        if token_data.get("expires_in"):
            token_expires_at = timezone.now() + timezone.timedelta(
                seconds=int(token_data["expires_in"])
            )
        account, _ = SocialAccount.objects.update_or_create(
            agency=request.user.agency,
            provider=SocialAccount.PROVIDER_META,
            platform=SocialAccount.PLATFORM_WHATSAPP,
            external_id=values["phone_number_id"],
            defaults={
                "name": phone.get("verified_name") or "WhatsApp Business",
                "username": None,
                "page_id": None,
                "business_account_id": values["business_account_id"],
                "phone_number_id": values["phone_number_id"],
                "display_phone_number": phone.get("display_phone_number") or "",
                "quality_rating": phone.get("quality_rating") or "",
                "access_token": access_token,
                "user_access_token": "",
                "token_expires_at": token_expires_at,
                "scopes": "whatsapp_business_management,whatsapp_business_messaging",
                "status": SocialAccount.STATUS_CONNECTED,
                "connected_by": request.user,
                "webhook_subscription_status": "subscribed",
                "webhook_subscribed_at": timezone.now(),
                "webhook_error": "",
            },
        )
        oauth_state.mark_used()
        return Response(SocialAccountSerializer(account).data)


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
        require_social_connection_manager(user)

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
