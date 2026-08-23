import json
import tempfile
from io import BytesIO
from unittest.mock import call, patch

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from agencies.models import Agency
from social_media.models import (
    SocialAccount,
    SocialPost,
    SocialPostMedia,
    SocialPublishResult,
)
from social_media.services.publishing import publish_social_post
from users.models import AgencyUser


def image_bytes(size=(1080, 1080), color="white"):
    buffer = BytesIO()
    Image.new("RGB", size, color=color).save(buffer, format="JPEG")
    return buffer.getvalue()


def uploaded_image(name, size=(1080, 1080), color="white"):
    return SimpleUploadedFile(
        name,
        image_bytes(size=size, color=color),
        content_type="image/jpeg",
    )


class SocialPostMultiImageTestCase(APITestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.media_override.enable()

        self.agency = Agency.objects.create(
            name="Carousel Realty",
            license_number="CAR-001",
        )
        self.owner = AgencyUser.objects.create_user(
            email="carousel-owner@example.com",
            password="Password123",
            full_name="Carousel Owner",
            agency=self.agency,
            role=AgencyUser.ROLE_AGENCY_OWNER,
        )
        self.facebook_account = SocialAccount.objects.create(
            agency=self.agency,
            provider=SocialAccount.PROVIDER_META,
            platform=SocialAccount.PLATFORM_FACEBOOK,
            external_id="page-carousel",
            page_id="page-carousel",
            name="Carousel Page",
            access_token="page-token",
        )
        self.instagram_account = SocialAccount.objects.create(
            agency=self.agency,
            provider=SocialAccount.PROVIDER_META,
            platform=SocialAccount.PLATFORM_INSTAGRAM,
            external_id="ig-carousel",
            page_id="page-carousel",
            name="Carousel Instagram",
            access_token="page-token",
        )
        self.client.force_authenticate(user=self.owner)

    def tearDown(self):
        self.media_override.disable()
        self.media_directory.cleanup()

    def create_post_with_media(self, count=3, account=None):
        account = account or self.facebook_account
        post = SocialPost.objects.create(
            agency=self.agency,
            social_account=account,
            platform=account.platform,
            caption="Ordered property gallery",
            created_by=self.owner,
        )
        for index in range(count):
            SocialPostMedia.objects.create(
                post=post,
                image=ContentFile(
                    image_bytes(color=(index * 30, index * 30, index * 30)),
                    name=f"gallery-{index + 1}.jpg",
                ),
                position=index,
            )
        first_item = post.media_items.first()
        post.image.name = first_item.image.name
        post.save(update_fields=["image"])
        return post

    def test_create_accepts_five_ordered_images_and_sets_cover_alias(self):
        images = [uploaded_image(f"image-{index}.jpg") for index in range(5)]
        response = self.client.post(
            reverse("social-post-list-create"),
            {
                "social_account": self.facebook_account.id,
                "platform": SocialPost.PLATFORM_FACEBOOK,
                "caption": "Five image carousel",
                "status": SocialPost.STATUS_DRAFT,
                "images": images,
                "media_order": json.dumps([f"new:{index}" for index in range(5)]),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(len(response.data["media"]), 5)
        post = SocialPost.objects.get(pk=response.data["id"])
        self.assertEqual(post.media_items.count(), 5)
        self.assertEqual(post.image.name, post.media_items.first().image.name)

    def test_create_rejects_more_than_five_images(self):
        response = self.client.post(
            reverse("social-post-list-create"),
            {
                "social_account": self.facebook_account.id,
                "platform": SocialPost.PLATFORM_FACEBOOK,
                "caption": "Too many images",
                "images": [uploaded_image(f"image-{index}.jpg") for index in range(6)],
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("images", response.data)

    def test_create_rejects_image_outside_supported_aspect_ratio(self):
        response = self.client.post(
            reverse("social-post-list-create"),
            {
                "social_account": self.facebook_account.id,
                "platform": SocialPost.PLATFORM_FACEBOOK,
                "caption": "Invalid ratio",
                "images": [uploaded_image("too-tall.jpg", size=(1080, 1800))],
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("4:5", str(response.data["images"]))

    def test_edit_can_reorder_and_remove_draft_images(self):
        post = self.create_post_with_media(count=3)
        media = list(post.media_items.all())

        response = self.client.patch(
            reverse("social-post-detail", kwargs={"pk": post.id}),
            {
                "media_order": json.dumps(
                    [f"existing:{media[2].id}", f"existing:{media[0].id}"]
                )
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        post.refresh_from_db()
        remaining = list(post.media_items.all())
        self.assertEqual([item.id for item in remaining], [media[2].id, media[0].id])
        self.assertEqual([item.position for item in remaining], [0, 1])
        self.assertEqual(post.image.name, remaining[0].image.name)

    def test_edit_rejects_carousel_changes_after_publish(self):
        post = self.create_post_with_media(count=2)
        media = list(post.media_items.all())
        SocialPublishResult.objects.create(
            post=post,
            social_account=self.facebook_account,
            platform=SocialAccount.PLATFORM_FACEBOOK,
            status=SocialPublishResult.STATUS_PUBLISHED,
            external_post_id="page-carousel_post-1",
        )

        response = self.client.patch(
            reverse("social-post-detail", kwargs={"pk": post.id}),
            {"media_order": json.dumps([f"existing:{media[1].id}"])},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "published_media_is_immutable")

    @patch(
        "social_media.views.delete_facebook_post",
        return_value={"success": True},
    )
    def test_delete_facebook_carousel_targets_combined_post(self, delete_mock):
        post = self.create_post_with_media(count=3)
        SocialPublishResult.objects.create(
            post=post,
            social_account=self.facebook_account,
            platform=SocialAccount.PLATFORM_FACEBOOK,
            status=SocialPublishResult.STATUS_PUBLISHED,
            external_post_id="page-carousel_post-1",
            external_media_id="photo-1",
        )

        response = self.client.delete(
            reverse("social-post-detail", kwargs={"pk": post.id})
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        delete_mock.assert_called_once_with(
            post_id="page-carousel_post-1",
            page_access_token="page-token",
        )

    @patch(
        "social_media.services.publishing.publish_facebook_multi_photo_post",
        return_value={"id": "page-carousel_post-1"},
    )
    @patch("social_media.services.publishing.upload_facebook_unpublished_photo")
    def test_facebook_publishes_one_multi_photo_post(
        self,
        upload_mock,
        publish_mock,
    ):
        post = self.create_post_with_media(count=3)
        upload_mock.side_effect = [
            {"id": "photo-1"},
            {"id": "photo-2"},
            {"id": "photo-3"},
        ]

        publish_social_post(post, platforms=[SocialPost.PLATFORM_FACEBOOK])

        self.assertEqual(upload_mock.call_count, 3)
        publish_mock.assert_called_once_with(
            page_id="page-carousel",
            page_access_token="page-token",
            photo_ids=["photo-1", "photo-2", "photo-3"],
            message="Ordered property gallery",
        )
        result = SocialPublishResult.objects.get(post=post)
        self.assertEqual(result.external_post_id, "page-carousel_post-1")
        self.assertEqual(result.external_media_id, "photo-1")

    @patch(
        "social_media.services.publishing.publish_instagram_container",
        return_value={"id": "ig-carousel-media"},
    )
    @patch(
        "social_media.services.publishing.create_instagram_carousel_container",
        return_value={"id": "carousel-parent"},
    )
    @patch(
        "social_media.services.publishing.get_instagram_container_status",
        return_value={"status_code": "FINISHED"},
    )
    @patch("social_media.services.publishing.create_instagram_image_container")
    @patch("social_media.services.publishing.get_public_image_url")
    def test_instagram_publishes_children_under_one_carousel_parent(
        self,
        public_url_mock,
        child_mock,
        status_mock,
        parent_mock,
        publish_mock,
    ):
        post = self.create_post_with_media(count=3, account=self.instagram_account)
        public_url_mock.side_effect = [
            "https://cdn.example.com/1.jpg",
            "https://cdn.example.com/2.jpg",
            "https://cdn.example.com/3.jpg",
        ]
        child_mock.side_effect = [
            {"id": "child-1"},
            {"id": "child-2"},
            {"id": "child-3"},
        ]

        publish_social_post(post, platforms=[SocialPost.PLATFORM_INSTAGRAM])

        self.assertEqual(child_mock.call_count, 3)
        self.assertEqual(
            [item.kwargs["is_carousel_item"] for item in child_mock.call_args_list],
            [True, True, True],
        )
        parent_mock.assert_called_once_with(
            instagram_account_id="ig-carousel",
            page_access_token="page-token",
            child_container_ids=["child-1", "child-2", "child-3"],
            caption="Ordered property gallery",
        )
        self.assertEqual(
            status_mock.call_args_list,
            [
                call(container_id="child-1", page_access_token="page-token"),
                call(container_id="child-2", page_access_token="page-token"),
                call(container_id="child-3", page_access_token="page-token"),
                call(container_id="carousel-parent", page_access_token="page-token"),
            ],
        )
        publish_mock.assert_called_once_with(
            instagram_account_id="ig-carousel",
            page_access_token="page-token",
            container_id="carousel-parent",
        )

    @patch(
        "social_media.services.publishing.publish_instagram_images",
        return_value=("instagram-parent", "instagram-media"),
    )
    @patch(
        "social_media.services.publishing.publish_facebook_images",
        return_value=({"id": "facebook-post"}, "facebook-photo-1"),
    )
    def test_same_five_image_post_can_publish_to_facebook_and_instagram(
        self,
        facebook_mock,
        instagram_mock,
    ):
        post = self.create_post_with_media(count=5, account=self.facebook_account)
        post.target_platforms = ["facebook", "instagram"]
        post.save(update_fields=["target_platforms"])

        publish_social_post(post, platforms=["facebook", "instagram"])

        post.refresh_from_db()
        self.assertEqual(post.status, SocialPost.STATUS_PUBLISHED)
        self.assertEqual(len(facebook_mock.call_args.args[2]), 5)
        instagram_mock.assert_called_once()
        self.assertEqual(
            set(post.publish_results.values_list("platform", flat=True)),
            {"facebook", "instagram"},
        )
