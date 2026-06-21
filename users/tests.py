from django.urls import reverse
from django.contrib.auth import get_user_model

from rest_framework import status
from rest_framework.test import APITestCase

from agencies.models import Agency


User = get_user_model()


class AgentManagementAPITestCase(APITestCase):
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

        self.client.force_authenticate(user=self.owner)

    def test_agency_owner_can_create_agent(self):
        url = reverse("agent-list-create")

        payload = {
            "full_name": "Ram Agent",
            "email": "ram.agent@nexora.com",
            "password": "Password123",
        }

        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        agent = User.objects.get(email="ram.agent@nexora.com")

        self.assertEqual(agent.full_name, "Ram Agent")
        self.assertEqual(agent.role, "agent")
        self.assertEqual(agent.agency, self.agency)
        self.assertTrue(agent.is_active)

    def test_agency_owner_can_list_only_own_agents(self):
        User.objects.create_user(
            email="agent1@nexora.com",
            password="Password123",
            full_name="Agent One",
            agency=self.agency,
            role="agent",
        )

        other_agency = Agency.objects.create(
            name="Other Realty",
            license_number="OR-001",
        )

        User.objects.create_user(
            email="other.agent@nexora.com",
            password="Password123",
            full_name="Other Agent",
            agency=other_agency,
            role="agent",
        )

        url = reverse("agent-list-create")

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["email"], "agent1@nexora.com")

    def test_agent_cannot_create_another_agent(self):
        agent = User.objects.create_user(
            email="agent@nexora.com",
            password="Password123",
            full_name="Normal Agent",
            agency=self.agency,
            role="agent",
        )

        self.client.force_authenticate(user=agent)

        url = reverse("agent-list-create")

        payload = {
            "full_name": "Second Agent",
            "email": "second.agent@nexora.com",
            "password": "Password123",
        }

        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(
            User.objects.filter(email="second.agent@nexora.com").exists()
        )

    def test_agency_owner_can_soft_delete_agent(self):
        agent = User.objects.create_user(
            email="agent@nexora.com",
            password="Password123",
            full_name="Agent User",
            agency=self.agency,
            role="agent",
        )

        url = reverse("agent-detail", kwargs={"pk": agent.id})

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        agent.refresh_from_db()

        self.assertFalse(agent.is_active)
        self.assertTrue(User.objects.filter(id=agent.id).exists())

    def test_duplicate_agent_email_is_rejected(self):
        User.objects.create_user(
            email="agent@nexora.com",
            password="Password123",
            full_name="Agent User",
            agency=self.agency,
            role="agent",
        )

        url = reverse("agent-list-create")

        payload = {
            "full_name": "Duplicate Agent",
            "email": "agent@nexora.com",
            "password": "Password123",
        }

        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)