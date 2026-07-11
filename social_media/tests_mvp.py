from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from agencies.models import Agency
from social_media.models import SocialAccount, SocialPost
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
