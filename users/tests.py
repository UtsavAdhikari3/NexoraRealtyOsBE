from django.core.cache import cache
from django.urls import reverse
from django.contrib.auth import get_user_model

from rest_framework import status
from rest_framework.test import APITestCase

from agencies.models import Agency


User = get_user_model()


class AuthenticationThrottleAPITestCase(APITestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_repeated_login_attempts_are_throttled(self):
        url = reverse("login")
        payload = {
            "email": "missing@example.com",
            "password": "IncorrectPassword123",
        }

        responses = [
            self.client.post(url, payload, format="json")
            for _ in range(11)
        ]

        self.assertTrue(
            all(
                response.status_code == status.HTTP_401_UNAUTHORIZED
                for response in responses[:10]
            )
        )
        self.assertEqual(
            responses[10].status_code,
            status.HTTP_429_TOO_MANY_REQUESTS,
        )


class AgentRolePermissionAPITestCase(APITestCase):
    def setUp(self):
        self.agency = Agency.objects.create(
            name="Nexora Realty",
            license_number="NR-USER-ROLE-001",
        )

        self.owner = User.objects.create_user(
            email="owner.userrole@nexora.com",
            password="Password123",
            full_name="Agency Owner",
            agency=self.agency,
            role="agency_owner",
        )

        self.manager = User.objects.create_user(
            email="manager.userrole@nexora.com",
            password="Password123",
            full_name="Agency Manager",
            agency=self.agency,
            role="agency_manager",
        )

        self.agent = User.objects.create_user(
            email="agent.userrole@nexora.com",
            password="Password123",
            full_name="Agent User",
            agency=self.agency,
            role="agent",
        )

    def test_owner_can_create_agent(self):
        self.client.force_authenticate(user=self.owner)

        url = reverse("agent-list-create")

        payload = {
            "full_name": "New Agent",
            "email": "new.agent@nexora.com",
            "password": "Password123",
        }

        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.assertTrue(
            User.objects.filter(
                email="new.agent@nexora.com",
                role="agent",
                agency=self.agency,
            ).exists()
        )

    def test_manager_can_create_agent(self):
        self.client.force_authenticate(user=self.manager)

        url = reverse("agent-list-create")

        payload = {
            "full_name": "Manager Created Agent",
            "email": "manager.created.agent@nexora.com",
            "password": "Password123",
        }

        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_agent_cannot_create_agent(self):
        self.client.force_authenticate(user=self.agent)

        url = reverse("agent-list-create")

        payload = {
            "full_name": "Bad Agent",
            "email": "bad.agent@nexora.com",
            "password": "Password123",
        }

        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_cannot_change_agent_role_using_patch(self):
        self.client.force_authenticate(user=self.owner)

        url = reverse(
            "agent-detail",
            kwargs={"pk": self.agent.id}
        )

        payload = {
            "role": "agency_owner",
            "full_name": "Updated Agent Name",
        }

        response = self.client.patch(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.agent.refresh_from_db()

        self.assertEqual(self.agent.role, "agent")
        self.assertEqual(self.agent.full_name, "Updated Agent Name")

    def test_owner_can_soft_delete_agent(self):
        self.client.force_authenticate(user=self.owner)

        url = reverse(
            "agent-detail",
            kwargs={"pk": self.agent.id}
        )

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        self.agent.refresh_from_db()

        self.assertFalse(self.agent.is_active)
