from unittest.mock import patch
from io import BytesIO

from django.core.files.base import ContentFile
from django.test import override_settings
from django.urls import reverse
from urllib.parse import parse_qs, urlsplit
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from agencies.models import Agency
from social_media.models import (
    SocialAccount,
    SocialOAuthState,
    SocialPost,
    SocialPublishResult,
)
from social_media.services.meta import MetaAPIError
from users.models import AgencyUser


class SocialPublishingMVPAPITestCase(APITestCase):
    def setUp(self):
        self.agency = Agency.objects.create(name="Social Realty", license_number="SOC-001")
        self.other_agency = Agency.objects.create(name="Other Social", license_number="SOC-002")
        self.owner = AgencyUser.objects.create_user(
            email="social-owner@example.com",
            password="Password123",
            full_name="Social Owner",
            agency=self.agency,
            role=AgencyUser.ROLE_AGENCY_OWNER,
        )
        self.account = SocialAccount.objects.create(
            agency=self.agency,
            provider=SocialAccount.PROVIDER_META,
            platform=SocialAccount.PLATFORM_FACEBOOK,
            external_id="page-123",
            page_id="page-123",
            name="Social Page",
            access_token="test-token",
        )
        self.post = SocialPost.objects.create(
            agency=self.agency,
            social_account=self.account,
            platform=SocialPost.PLATFORM_FACEBOOK,
            caption="New property available",
            created_by=self.owner,
        )
        self.instagram_account = SocialAccount.objects.create(
            agency=self.agency,
            provider=SocialAccount.PROVIDER_META,
            platform=SocialAccount.PLATFORM_INSTAGRAM,
            external_id="ig-123",
            page_id="page-123",
            name="Nexora Instagram",
            username="nexorarealtyos",
            access_token="test-page-token",
        )

    def tearDown(self):
        if self.post.image:
            self.post.image.delete(save=False)

    def attach_test_image(self):
        buffer = BytesIO()
        Image.new("RGB", (1080, 1080), color="white").save(buffer, format="JPEG")
        self.post.image.save(
            "property.jpg",
            ContentFile(buffer.getvalue()),
            save=True,
        )

    @patch(
        "social_media.services.publishing.publish_facebook_feed_post",
        return_value={"id": "page-123_456"},
    )
    def test_publish_facebook_post(self, publish_mock):
        self.client.force_authenticate(user=self.owner)
        response = self.client.post(
            reverse("social-post-publish", kwargs={"pk": self.post.id}),
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, SocialPost.STATUS_PUBLISHED)
        self.assertEqual(self.post.external_post_id, "page-123_456")
        publish_mock.assert_called_once()

    @patch(
        "social_media.services.publishing.publish_instagram_container",
        return_value={"id": "ig-media-456"},
    )
    @patch(
        "social_media.services.publishing.get_instagram_container_status",
        return_value={"status_code": "FINISHED"},
    )
    @patch(
        "social_media.services.publishing.create_instagram_image_container",
        return_value={"id": "ig-container-123"},
    )
    @patch(
        "social_media.services.publishing.publish_facebook_photo_post",
        return_value={"id": "page-123_456"},
    )
    @patch("social_media.services.publishing.settings.PUBLIC_API_BASE_URL", "https://api.example.com")
    def test_publish_same_post_to_facebook_and_instagram(
        self,
        facebook_mock,
        create_container_mock,
        status_mock,
        instagram_publish_mock,
    ):
        self.attach_test_image()
        self.client.force_authenticate(user=self.owner)

        with patch(
            "social_media.services.publishing.get_public_image_url",
            return_value="https://api.example.com/media/property.jpg",
        ):
            response = self.client.post(
                reverse("social-post-publish", kwargs={"pk": self.post.id}),
                {"platforms": ["facebook", "instagram"]},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, SocialPost.STATUS_PUBLISHED)
        results = SocialPublishResult.objects.filter(post=self.post)
        self.assertEqual(results.filter(status="published").count(), 2)
        self.assertEqual(
            results.get(platform="instagram").container_id,
            "ig-container-123",
        )
        facebook_mock.assert_called_once()
        create_container_mock.assert_called_once()
        status_mock.assert_called_once()
        instagram_publish_mock.assert_called_once()

    @patch(
        "social_media.services.publishing.publish_instagram_container",
        return_value={"id": "ig-media-after-retry"},
    )
    @patch(
        "social_media.services.publishing.get_instagram_container_status",
        return_value={"status_code": "FINISHED"},
    )
    @patch("social_media.services.publishing.create_instagram_image_container")
    @patch(
        "social_media.services.publishing.publish_facebook_photo_post",
        return_value={"id": "page-123_789"},
    )
    @patch("social_media.services.publishing.settings.PUBLIC_API_BASE_URL", "https://api.example.com")
    def test_partial_failure_retries_only_failed_instagram_target(
        self,
        facebook_mock,
        create_container_mock,
        status_mock,
        instagram_publish_mock,
    ):
        self.attach_test_image()
        create_container_mock.side_effect = [
            ValueError("Instagram temporarily failed"),
            {"id": "retry-container"},
        ]
        self.client.force_authenticate(user=self.owner)
        url = reverse("social-post-publish", kwargs={"pk": self.post.id})
        payload = {"platforms": ["facebook", "instagram"]}

        with patch(
            "social_media.services.publishing.get_public_image_url",
            return_value="https://api.example.com/media/property.jpg",
        ):
            first = self.client.post(url, payload, format="json")
        self.assertEqual(first.status_code, status.HTTP_207_MULTI_STATUS)
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, SocialPost.STATUS_PARTIAL)

        with patch(
            "social_media.services.publishing.get_public_image_url",
            return_value="https://api.example.com/media/property.jpg",
        ):
            second = self.client.post(url, payload, format="json")
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, SocialPost.STATUS_PUBLISHED)
        self.assertEqual(facebook_mock.call_count, 1)
        self.assertEqual(
            SocialPublishResult.objects.get(
                post=self.post,
                platform="instagram",
            ).attempt_count,
            2,
        )

    @patch(
        "social_media.views.get_instagram_account_from_page",
        return_value={"id": "ig-discovered", "username": "nexorarealtyos", "name": "Nexora"},
    )
    @patch(
        "social_media.views.get_facebook_pages",
        return_value=[{"id": "page-discovered", "name": "Page", "access_token": "page-token"}],
    )
    @patch(
        "social_media.views.exchange_short_token_for_long_token",
        return_value={"access_token": "long-token"},
    )
    @patch(
        "social_media.views.exchange_code_for_short_token",
        return_value={"access_token": "short-token"},
    )
    @override_settings(
        FRONTEND_SOCIAL_SUCCESS_URL="http://localhost:5173/social-media"
    )
    def test_oauth_callback_discovers_and_stores_instagram_account(
        self,
        short_token_mock,
        long_token_mock,
        pages_mock,
        instagram_mock,
    ):
        oauth_state = SocialOAuthState.create_state(
            provider=SocialAccount.PROVIDER_META,
            agency=self.agency,
            user=self.owner,
        )
        with patch(
            "social_media.views.subscribe_page_to_webhooks",
            return_value={"success": True},
        ):
            response = self.client.get(
                reverse("meta-connection-callback"),
                {"code": "test-code", "state": oauth_state.state},
            )
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        redirect_parts = urlsplit(response["Location"])
        self.assertEqual(
            f"{redirect_parts.scheme}://{redirect_parts.netloc}{redirect_parts.path}",
            "http://localhost:5173/social-media",
        )
        self.assertEqual(
            parse_qs(redirect_parts.query),
            {
                "meta_connection": ["success"],
                "connected_count": ["2"],
                "warning_count": ["0"],
            },
        )
        instagram = SocialAccount.objects.get(
            agency=self.agency,
            platform=SocialAccount.PLATFORM_INSTAGRAM,
            external_id="ig-discovered",
        )
        self.assertEqual(instagram.page_id, "page-discovered")
        self.assertEqual(instagram.username, "nexorarealtyos")

    @override_settings(
        FRONTEND_SOCIAL_SUCCESS_URL="http://localhost:5173/social-media"
    )
    @patch(
        "social_media.views.get_instagram_account_from_page",
        return_value=None,
    )
    @patch(
        "social_media.views.get_facebook_pages",
        return_value=[
            {"id": "page-warning", "name": "Page", "access_token": "page-token"}
        ],
    )
    @patch(
        "social_media.views.exchange_short_token_for_long_token",
        return_value={"access_token": "long-token"},
    )
    @patch(
        "social_media.views.exchange_code_for_short_token",
        return_value={"access_token": "short-token"},
    )
    def test_oauth_callback_redirect_reports_connection_warnings(
        self,
        short_token_mock,
        long_token_mock,
        pages_mock,
        instagram_mock,
    ):
        oauth_state = SocialOAuthState.create_state(
            provider=SocialAccount.PROVIDER_META,
            agency=self.agency,
            user=self.owner,
        )
        with patch(
            "social_media.views.subscribe_page_to_webhooks",
            side_effect=MetaAPIError("Missing pages_messaging permission.", code=200),
        ):
            response = self.client.get(
                reverse("meta-connection-callback"),
                {"code": "test-code", "state": oauth_state.state},
            )

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(
            parse_qs(urlsplit(response["Location"]).query),
            {
                "meta_connection": ["success"],
                "connected_count": ["1"],
                "warning_count": ["1"],
            },
        )

    def test_cannot_select_another_agencys_social_account(self):
        other_account = SocialAccount.objects.create(
            agency=self.other_agency,
            provider=SocialAccount.PROVIDER_META,
            platform=SocialAccount.PLATFORM_FACEBOOK,
            external_id="other-page",
            access_token="other-token",
        )
        self.client.force_authenticate(user=self.owner)
        response = self.client.post(
            reverse("social-post-list-create"),
            {
                "platform": "facebook",
                "caption": "Invalid account",
                "social_account": other_account.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_target_platforms_requires_a_list_in_json(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(
            reverse("social-post-detail", kwargs={"pk": self.post.id}),
            {"target_platforms": "facebook"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["target_platforms"][0].code,
            "not_a_list",
        )

    def test_target_platforms_accepts_and_deduplicates_a_json_list(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(
            reverse("social-post-detail", kwargs={"pk": self.post.id}),
            {"target_platforms": ["facebook", "instagram", "facebook"]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["target_platforms"], ["facebook", "instagram"])

    @patch(
        "social_media.views.update_facebook_post",
        return_value={"success": True},
    )
    def test_edit_published_facebook_post_updates_meta_before_local_post(
        self,
        update_mock,
    ):
        self.post.status = SocialPost.STATUS_PUBLISHED
        self.post.save(update_fields=["status"])
        SocialPublishResult.objects.create(
            post=self.post,
            social_account=self.account,
            platform=SocialAccount.PLATFORM_FACEBOOK,
            status=SocialPublishResult.STATUS_PUBLISHED,
            external_post_id="page-123_456",
        )
        self.client.force_authenticate(user=self.owner)

        response = self.client.patch(
            reverse("social-post-detail", kwargs={"pk": self.post.id}),
            {"caption": "Updated property caption"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.post.refresh_from_db()
        self.assertEqual(self.post.caption, "Updated property caption")
        update_mock.assert_called_once_with(
            post_id="page-123_456",
            page_access_token="test-token",
            message="Updated property caption",
        )

    @patch(
        "social_media.views.update_facebook_post",
        side_effect=MetaAPIError("Token expired", code=190),
    )
    def test_edit_keeps_local_caption_when_facebook_update_fails(self, update_mock):
        self.post.status = SocialPost.STATUS_PUBLISHED
        self.post.save(update_fields=["status"])
        SocialPublishResult.objects.create(
            post=self.post,
            social_account=self.account,
            platform=SocialAccount.PLATFORM_FACEBOOK,
            status=SocialPublishResult.STATUS_PUBLISHED,
            external_post_id="page-123_456",
        )
        self.client.force_authenticate(user=self.owner)

        response = self.client.patch(
            reverse("social-post-detail", kwargs={"pk": self.post.id}),
            {"caption": "Should not be saved"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.post.refresh_from_db()
        self.assertEqual(self.post.caption, "New property available")
        self.assertEqual(response.data["meta_error"]["code"], 190)

    @patch(
        "social_media.views.delete_facebook_post",
        return_value={"success": True},
    )
    def test_delete_published_facebook_post_deletes_meta_before_local_post(
        self,
        delete_mock,
    ):
        SocialPublishResult.objects.create(
            post=self.post,
            social_account=self.account,
            platform=SocialAccount.PLATFORM_FACEBOOK,
            status=SocialPublishResult.STATUS_PUBLISHED,
            external_post_id="page-123_456",
        )
        self.client.force_authenticate(user=self.owner)

        response = self.client.delete(
            reverse("social-post-detail", kwargs={"pk": self.post.id})
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(SocialPost.objects.filter(pk=self.post.id).exists())
        delete_mock.assert_called_once_with(
            post_id="page-123_456",
            page_access_token="test-token",
        )

    @patch(
        "social_media.views.delete_facebook_post",
        side_effect=MetaAPIError("Permission denied", code=200),
    )
    def test_delete_keeps_local_post_when_facebook_delete_fails(self, delete_mock):
        SocialPublishResult.objects.create(
            post=self.post,
            social_account=self.account,
            platform=SocialAccount.PLATFORM_FACEBOOK,
            status=SocialPublishResult.STATUS_PUBLISHED,
            external_post_id="page-123_456",
        )
        self.client.force_authenticate(user=self.owner)

        response = self.client.delete(
            reverse("social-post-detail", kwargs={"pk": self.post.id})
        )

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertTrue(SocialPost.objects.filter(pk=self.post.id).exists())
        self.assertEqual(response.data["meta_error"]["code"], 200)
