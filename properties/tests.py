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

class PropertyAgentAssignmentAPITestCase(APITestCase):
    def setUp(self):
        self.agency = Agency.objects.create(
            name="Nexora Realty",
            license_number="NR-001",
        )

        self.owner = User.objects.create_user(
            email="owner@nexora.com",
            password="Password123",
            full_name="Agency Owner",
            agency=self.agency,
            role="agency_owner",
        )

        self.agent = User.objects.create_user(
            email="agent@nexora.com",
            password="Password123",
            full_name="Agent User",
            agency=self.agency,
            role="agent",
        )

        self.property = Property.objects.create(
            agency=self.agency,
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

        self.client.force_authenticate(user=self.owner)

    def test_owner_can_assign_property_to_agent(self):
        url = reverse(
            "property-detail",
            kwargs={"pk": self.property.id}
        )

        payload = {
            "assigned_agent": self.agent.id
        }

        response = self.client.patch(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.property.refresh_from_db()

        self.assertEqual(self.property.assigned_agent, self.agent)

    def test_owner_cannot_assign_property_to_agent_from_other_agency(self):
        other_agency = Agency.objects.create(
            name="Other Realty",
            license_number="OR-001",
        )

        other_agent = User.objects.create_user(
            email="other.agent@nexora.com",
            password="Password123",
            full_name="Other Agent",
            agency=other_agency,
            role="agent",
        )

        url = reverse(
            "property-detail",
            kwargs={"pk": self.property.id}
        )

        payload = {
            "assigned_agent": other_agent.id
        }

        response = self.client.patch(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.property.refresh_from_db()

        self.assertIsNone(self.property.assigned_agent)

class PropertyFilterAPITestCase(APITestCase):
    def setUp(self):
        self.agency = Agency.objects.create(
            name="Nexora Realty",
            license_number="NR-001",
        )

        self.owner = User.objects.create_user(
            email="owner.filters@nexora.com",
            password="Password123",
            full_name="Agency Owner",
            agency=self.agency,
            role="agency_owner",
        )

        self.agent = User.objects.create_user(
            email="agent.filters@nexora.com",
            password="Password123",
            full_name="Ram Agent",
            agency=self.agency,
            role="agent",
        )

        self.house = Property.objects.create(
            agency=self.agency,
            assigned_agent=self.agent,
            title="Modern House in Kathmandu",
            property_type="house",
            purpose="sale",
            price=15000000,
            province="Bagmati",
            district="Kathmandu",
            city="Kathmandu",
            neighbourhood="Milan Chowk",
            address="House no. 24",
            bedrooms=3,
            bathrooms=2,
            description="Beautiful house.",
            status="available",
        )

        self.land = Property.objects.create(
            agency=self.agency,
            title="Land in Bhaktapur",
            property_type="land",
            purpose="sale",
            price=8000000,
            province="Bagmati",
            district="Bhaktapur",
            city="Bhaktapur",
            neighbourhood="Suryabinayak",
            address="Near main road",
            bedrooms=0,
            bathrooms=0,
            description="Good land.",
            status="draft",
        )

        self.apartment = Property.objects.create(
            agency=self.agency,
            title="Apartment in Lalitpur",
            property_type="apartment",
            purpose="rent",
            price=50000,
            province="Bagmati",
            district="Lalitpur",
            city="Lalitpur",
            neighbourhood="Jawalakhel",
            address="Near zoo",
            bedrooms=2,
            bathrooms=1,
            description="Nice apartment.",
            status="available",
        )

        other_agency = Agency.objects.create(
            name="Other Realty",
            license_number="OR-FILTER-001",
        )

        Property.objects.create(
            agency=other_agency,
            title="Other Agency House",
            property_type="house",
            purpose="sale",
            price=10000000,
            province="Bagmati",
            district="Kathmandu",
            city="Kathmandu",
            neighbourhood="Other Area",
            address="Other address",
            bedrooms=3,
            bathrooms=2,
            description="Should not be visible.",
            status="available",
        )

        self.client.force_authenticate(user=self.owner)

    def get_results(self, response):
        if isinstance(response.data, dict) and "results" in response.data:
            return response.data["results"]

        return response.data

    def test_filter_by_property_type(self):
        url = reverse("property-list")

        response = self.client.get(
            url,
            {
                "property_type": "house"
            }
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = self.get_results(response)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.house.id)
        self.assertEqual(results[0]["property_type"], "house")

    def test_filter_by_status(self):
        url = reverse("property-list")

        response = self.client.get(
            url,
            {
                "status": "draft"
            }
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = self.get_results(response)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.land.id)
        self.assertEqual(results[0]["status"], "draft")

    def test_filter_by_location_city(self):
        url = reverse("property-list")

        response = self.client.get(
            url,
            {
                "location": "Bhaktapur"
            }
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = self.get_results(response)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.land.id)

    def test_filter_by_location_neighbourhood(self):
        url = reverse("property-list")

        response = self.client.get(
            url,
            {
                "location": "Milan Chowk"
            }
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = self.get_results(response)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.house.id)

    def test_filter_by_assigned_agent(self):
        url = reverse("property-list")

        response = self.client.get(
            url,
            {
                "assigned_agent": self.agent.id
            }
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = self.get_results(response)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.house.id)
        self.assertEqual(results[0]["assigned_agent"], self.agent.id)

    def test_filter_by_unassigned_agent(self):
        url = reverse("property-list")

        response = self.client.get(
            url,
            {
                "assigned_agent": "unassigned"
            }
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = self.get_results(response)

        result_ids = [
            item["id"]
            for item in results
        ]

        self.assertIn(self.land.id, result_ids)
        self.assertIn(self.apartment.id, result_ids)
        self.assertNotIn(self.house.id, result_ids)

    def test_filter_options_returns_property_types_statuses_locations_and_agents(self):
        url = reverse("property-filter-options")

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertIn("property_types", response.data)
        self.assertIn("statuses", response.data)
        self.assertIn("locations", response.data)
        self.assertIn("agents", response.data)

        location_values = [
            location["value"]
            for location in response.data["locations"]
        ]

        self.assertIn("Bagmati", location_values)
        self.assertIn("Kathmandu", location_values)
        self.assertIn("Bhaktapur", location_values)
        self.assertIn("Lalitpur", location_values)
        self.assertIn("Milan Chowk", location_values)
        self.assertIn("Suryabinayak", location_values)
        self.assertIn("Jawalakhel", location_values)

        agent_values = [
            agent["value"]
            for agent in response.data["agents"]
        ]

        self.assertIn(self.agent.id, agent_values)
        self.assertIn("unassigned", agent_values)

    def test_invalid_assigned_agent_filter_returns_empty_list(self):
        url = reverse("property-list")

        response = self.client.get(
            url,
            {
                "assigned_agent": "abc"
            }
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = self.get_results(response)

        self.assertEqual(len(results), 0)

class PropertyRolePermissionAPITestCase(APITestCase):
    def setUp(self):
        self.agency = Agency.objects.create(
            name="Nexora Realty",
            license_number="NR-ROLE-001",
        )

        self.owner = User.objects.create_user(
            email="owner.role@nexora.com",
            password="Password123",
            full_name="Agency Owner",
            agency=self.agency,
            role="agency_owner",
        )

        self.manager = User.objects.create_user(
            email="manager.role@nexora.com",
            password="Password123",
            full_name="Agency Manager",
            agency=self.agency,
            role="agency_manager",
        )

        self.agent = User.objects.create_user(
            email="agent.role@nexora.com",
            password="Password123",
            full_name="Agent User",
            agency=self.agency,
            role="agent",
        )

        self.other_agent = User.objects.create_user(
            email="other.agent.role@nexora.com",
            password="Password123",
            full_name="Other Agent",
            agency=self.agency,
            role="agent",
        )

        self.assigned_property = Property.objects.create(
            agency=self.agency,
            assigned_agent=self.agent,
            title="Assigned House",
            property_type="house",
            purpose="sale",
            price=15000000,
            province="Bagmati",
            district="Kathmandu",
            city="Kathmandu",
            address="Assigned address",
            bedrooms=3,
            bathrooms=2,
            description="Assigned property.",
            status="available",
            is_published=True,
        )

        self.unassigned_property = Property.objects.create(
            agency=self.agency,
            title="Unassigned Land",
            property_type="land",
            purpose="sale",
            price=8000000,
            province="Bagmati",
            district="Bhaktapur",
            city="Bhaktapur",
            address="Unassigned address",
            bedrooms=0,
            bathrooms=0,
            description="Unassigned property.",
            status="draft",
            is_published=False,
        )

    def test_agent_can_view_agency_properties(self):
        self.client.force_authenticate(user=self.agent)

        url = reverse("property-list")

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_agent_can_edit_assigned_property_allowed_field(self):
        self.client.force_authenticate(user=self.agent)

        url = reverse(
            "property-detail",
            kwargs={"pk": self.assigned_property.id}
        )

        payload = {
            "description": "Updated by assigned agent."
        }

        response = self.client.patch(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assigned_property.refresh_from_db()

        self.assertEqual(
            self.assigned_property.description,
            "Updated by assigned agent."
        )

    def test_agent_cannot_edit_unassigned_property(self):
        self.client.force_authenticate(user=self.agent)

        url = reverse(
            "property-detail",
            kwargs={"pk": self.unassigned_property.id}
        )

        payload = {
            "description": "Trying to update unassigned property."
        }

        response = self.client.patch(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_agent_cannot_publish_assigned_property(self):
        self.client.force_authenticate(user=self.agent)

        url = reverse(
            "property-detail",
            kwargs={"pk": self.assigned_property.id}
        )

        payload = {
            "is_published": True,
            "status": "available",
        }

        response = self.client.patch(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_agent_cannot_assign_property_to_other_agent(self):
        self.client.force_authenticate(user=self.agent)

        url = reverse(
            "property-detail",
            kwargs={"pk": self.assigned_property.id}
        )

        payload = {
            "assigned_agent": self.other_agent.id
        }

        response = self.client.patch(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_agent_cannot_delete_property(self):
        self.client.force_authenticate(user=self.agent)

        url = reverse(
            "property-detail",
            kwargs={"pk": self.assigned_property.id}
        )

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.assertTrue(
            Property.objects.filter(
                id=self.assigned_property.id
            ).exists()
        )

    def test_owner_can_delete_property(self):
        self.client.force_authenticate(user=self.owner)

        url = reverse(
            "property-detail",
            kwargs={"pk": self.unassigned_property.id}
        )

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_manager_can_update_any_agency_property(self):
        self.client.force_authenticate(user=self.manager)

        url = reverse(
            "property-detail",
            kwargs={"pk": self.unassigned_property.id}
        )

        payload = {
            "description": "Updated by manager."
        }

        response = self.client.patch(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.unassigned_property.refresh_from_db()

        self.assertEqual(
            self.unassigned_property.description,
            "Updated by manager."
        )

    def test_agent_created_property_is_forced_to_draft_and_assigned_to_self(self):
        self.client.force_authenticate(user=self.agent)

        url = reverse("property-list")

        payload = {
            "title": "Agent Created Property",
            "property_type": "house",
            "purpose": "sale",
            "price": "12000000.00",
            "province": "Bagmati",
            "district": "Kathmandu",
            "city": "Kathmandu",
            "address": "Agent address",
            "bedrooms": 2,
            "bathrooms": 1,
            "description": "Created by agent.",
            "status": "available",
            "is_published": True,
            "is_featured": True,
            "assigned_agent": self.other_agent.id,
        }

        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        created_property = Property.objects.get(
            title="Agent Created Property"
        )

        self.assertEqual(created_property.assigned_agent, self.agent)
        self.assertEqual(created_property.status, "draft")
        self.assertFalse(created_property.is_published)
        self.assertFalse(created_property.is_featured)