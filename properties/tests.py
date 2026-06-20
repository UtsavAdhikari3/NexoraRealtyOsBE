import shutil
import tempfile

from django.test import override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from rest_framework import status
from rest_framework.test import APITestCase

from agencies.models import Agency
from properties.models import Property, PropertyMedia


TEMP_MEDIA_ROOT = tempfile.mkdtemp()

User = get_user_model()


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class PropertyMediaAPITestCase(APITestCase):

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.agency = Agency.objects.create(
            name="Nexora Realty",
            license_number="NR-001",
        )

        self.user = User.objects.create_user(
            email="owner@nexora.com",
            password="Password123",
            full_name="Agency Owner",
            agency=self.agency,
            role="agency_owner",
        )

        self.property = Property.objects.create(
            agency=self.agency,
            assigned_agent=self.user,
            title="3 BHK House in Kathmandu",
            property_type="house",
            purpose="sale",
            price=15000000,
            province="Bagmati",
            district="Kathmandu",
            city="Kathmandu",
            address="Budhanilkantha",
            bedrooms=3,
            bathrooms=2,
            description="Beautiful family home.",
            status="available",
        )

        self.client.force_authenticate(user=self.user)

    def test_authenticated_user_can_upload_property_media(self):
        url = reverse(
            "property-media-list",
            kwargs={"property_id": self.property.id}
        )

        file = SimpleUploadedFile(
            "front.jpg",
            b"fake-image-content",
            content_type="image/jpeg"
        )

        payload = {
            "media_type": "image",
            "file": file,
            "title": "Front View",
            "caption": "Main front view",
            "sort_order": 1,
            "is_primary": True,
        }

        response = self.client.post(
            url,
            payload,
            format="multipart"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(PropertyMedia.objects.count(), 1)

        media = PropertyMedia.objects.first()

        self.assertEqual(media.property, self.property)
        self.assertEqual(media.agency, self.agency)
        self.assertEqual(media.media_type, "image")
        self.assertTrue(media.is_primary)

    def test_authenticated_user_can_list_property_media(self):
        PropertyMedia.objects.create(
            agency=self.agency,
            property=self.property,
            media_type="image",
            file="property_media/front.jpg",
            title="Front View",
            is_primary=True,
        )

        url = reverse(
            "property-media-list",
            kwargs={"property_id": self.property.id}
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["title"], "Front View")

    def test_user_cannot_upload_media_to_another_agency_property(self):
        other_agency = Agency.objects.create(
            name="Other Realty",
            license_number="OR-001",
        )

        other_property = Property.objects.create(
            agency=other_agency,
            title="Other Agency Property",
            property_type="land",
            purpose="sale",
            price=5000000,
            province="Bagmati",
            district="Lalitpur",
            city="Lalitpur",
            address="Patan",
            bedrooms=0,
            bathrooms=0,
            description="Other agency listing.",
            status="available",
        )

        url = reverse(
            "property-media-list",
            kwargs={"property_id": other_property.id}
        )

        file = SimpleUploadedFile(
            "land.jpg",
            b"fake-image-content",
            content_type="image/jpeg"
        )

        payload = {
            "media_type": "image",
            "file": file,
            "title": "Land Image",
        }

        response = self.client.post(
            url,
            payload,
            format="multipart"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(PropertyMedia.objects.count(), 0)

    def test_user_can_delete_own_property_media(self):
        media = PropertyMedia.objects.create(
            agency=self.agency,
            property=self.property,
            media_type="image",
            file="property_media/front.jpg",
            title="Front View",
        )

        url = reverse(
            "property-media-detail",
            kwargs={"pk": media.id}
        )

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(PropertyMedia.objects.count(), 0)

    def test_unauthenticated_user_cannot_upload_property_media(self):
        self.client.force_authenticate(user=None)

        url = reverse(
            "property-media-list",
            kwargs={"property_id": self.property.id}
        )

        file = SimpleUploadedFile(
            "front.jpg",
            b"fake-image-content",
            content_type="image/jpeg"
        )

        payload = {
            "media_type": "image",
            "file": file,
            "title": "Front View",
        }

        response = self.client.post(
            url,
            payload,
            format="multipart"
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)