import tempfile
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from agencies.models import Agency
from social_media.models import SocialAccount, SocialPost, SocialPublishResult
from social_media.services.video import CompressedReel, ReelValidationError, compress_reel_upload
from users.models import AgencyUser


class SocialReelTestCase(APITestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.media_override.enable()
        self.agency = Agency.objects.create(name="Reel Realty", license_number="REEL-001")
        self.owner = AgencyUser.objects.create_user(
            email="reel-owner@example.com",
            password="Password123",
            full_name="Reel Owner",
            agency=self.agency,
            role=AgencyUser.ROLE_AGENCY_OWNER,
        )
        self.facebook = SocialAccount.objects.create(
            agency=self.agency,
            provider=SocialAccount.PROVIDER_META,
            platform=SocialAccount.PLATFORM_FACEBOOK,
            external_id="page-reel",
            page_id="page-reel",
            name="Reel Page",
            access_token="page-token",
        )
        self.instagram = SocialAccount.objects.create(
            agency=self.agency,
            provider=SocialAccount.PROVIDER_META,
            platform=SocialAccount.PLATFORM_INSTAGRAM,
            external_id="ig-reel",
            page_id="page-reel",
            name="Reel Instagram",
            access_token="page-token",
        )
        self.client.force_authenticate(user=self.owner)

    def tearDown(self):
        self.media_override.disable()
        self.media_directory.cleanup()

    @patch("social_media.serializers.compress_reel_upload")
    def test_create_reel_stores_only_compressed_video_and_metadata(self, compress_mock):
        compressed_bytes = b"compressed-mp4"
        compress_mock.return_value = CompressedReel(
            file=ContentFile(compressed_bytes, name="listing-reel.mp4"),
            duration_seconds=42.5,
            width=720,
            height=1280,
            size_bytes=len(compressed_bytes),
        )
        response = self.client.post(
            reverse("social-post-list-create"),
            {
                "social_account": self.facebook.id,
                "platform": "facebook",
                "target_platforms": ["facebook", "instagram"],
                "post_format": "reel",
                "caption": "A new property Reel",
                "video": SimpleUploadedFile(
                    "source.mov",
                    b"large-original-video-placeholder",
                    content_type="video/quicktime",
                ),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        post = SocialPost.objects.get(pk=response.data["id"])
        self.assertEqual(post.post_format, SocialPost.FORMAT_REEL)
        self.assertEqual(post.video_duration_seconds, 42.5)
        self.assertEqual(post.video_size_bytes, len(compressed_bytes))
        with post.video.open("rb") as stored:
            self.assertEqual(stored.read(), compressed_bytes)

    def test_create_reel_requires_video(self):
        response = self.client.post(
            reverse("social-post-list-create"),
            {
                "social_account": self.facebook.id,
                "platform": "facebook",
                "post_format": "reel",
                "caption": "Missing video",
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("video", response.data)

    @patch("social_media.services.publishing.publish_instagram_reel")
    @patch("social_media.services.publishing.publish_facebook_reel")
    def test_publish_reel_to_facebook_and_instagram(self, facebook_mock, instagram_mock):
        facebook_mock.return_value = "fb-video-1"
        instagram_mock.return_value = ("ig-container-1", "ig-reel-1")
        post = SocialPost.objects.create(
            agency=self.agency,
            social_account=self.facebook,
            platform="facebook",
            target_platforms=["facebook", "instagram"],
            post_format=SocialPost.FORMAT_REEL,
            caption="Dual platform Reel",
            video=ContentFile(b"compressed", name="dual-reel.mp4"),
            video_duration_seconds=30,
            video_width=720,
            video_height=1280,
            video_size_bytes=10,
            created_by=self.owner,
        )
        response = self.client.post(
            reverse("social-post-publish", kwargs={"pk": post.id}),
            {"platforms": ["facebook", "instagram"]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        post.refresh_from_db()
        self.assertEqual(post.status, SocialPost.STATUS_PUBLISHED)
        self.assertEqual(
            set(post.publish_results.values_list("platform", flat=True)),
            {"facebook", "instagram"},
        )
        self.assertEqual(
            post.publish_results.filter(status=SocialPublishResult.STATUS_PUBLISHED).count(),
            2,
        )


class ReelCompressionGuardTestCase(SimpleTestCase):
    @override_settings(
        SOCIAL_REEL_MAX_SOURCE_SIZE_BYTES=1,
        SOCIAL_REEL_MAX_SOURCE_SIZE_MB=1,
    )
    def test_reel_source_size_is_checked_before_encoding(self):
        upload = SimpleUploadedFile("too-large.mp4", b"12", content_type="video/mp4")
        with self.assertRaisesMessage(ReelValidationError, "source video exceeds"):
            compress_reel_upload(upload)
