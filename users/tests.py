import re
from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.urls import reverse
from django.test import override_settings
from django.contrib.auth import get_user_model

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from agencies.models import Agency
from properties.models import Property


User = get_user_model()


class LogoutAPITestCase(APITestCase):
    def setUp(self):
        self.agency = Agency.objects.create(
            name="Logout Realty",
            license_number="LOGOUT-001",
            payment_status=Agency.PAYMENT_PAID,
        )
        self.user = User.objects.create_user(
            email="logout@nexora.com",
            password="Password123!",
            full_name="Logout User",
            agency=self.agency,
            role=User.ROLE_AGENCY_OWNER,
            is_email_verified=True,
        )

    def test_logout_blacklists_refresh_token(self):
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        response = self.client.post(reverse("logout"), {"refresh": str(refresh)}, format="json")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        self.client.credentials()
        refresh_response = self.client.post(reverse("token_refresh"), {"refresh": str(refresh)}, format="json")
        self.assertEqual(refresh_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_rejects_another_users_refresh_token(self):
        other = User.objects.create_user(
            email="other.logout@nexora.com",
            password="Password123!",
            full_name="Other User",
            agency=self.agency,
            role=User.ROLE_AGENT,
            is_email_verified=True,
        )
        access = RefreshToken.for_user(self.user).access_token
        other_refresh = RefreshToken.for_user(other)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        response = self.client.post(reverse("logout"), {"refresh": str(other_refresh)}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


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


class EmailNormalizationAPITestCase(APITestCase):
    def setUp(self):
        cache.clear()
        self.agency = Agency.objects.create(
            name="Email Case Realty",
            license_number="EMAIL-CASE-001",
            payment_status=Agency.PAYMENT_PAID,
        )

    def tearDown(self):
        cache.clear()

    def test_user_creation_normalizes_the_entire_email_address(self):
        user = User.objects.create_user(
            email="  Case.Sensitive@Example.COM  ",
            password="Case-Normalization-2026",
            full_name="Case User",
            agency=self.agency,
            role=User.ROLE_AGENCY_OWNER,
        )

        self.assertEqual(user.email, "case.sensitive@example.com")

    def test_login_accepts_any_email_capitalization(self):
        user = User.objects.create_user(
            email="mixed.case@example.com",
            password="Case-Normalization-2026",
            full_name="Mixed Case User",
            agency=self.agency,
            role=User.ROLE_AGENCY_OWNER,
            is_email_verified=True,
        )

        response = self.client.post(
            reverse("login"),
            {"email": "MIXED.CASE@EXAMPLE.COM", "password": "Case-Normalization-2026"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["id"], user.id)


class AgentOTPEnvironmentPolicyTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.agency = Agency.objects.create(
            name="Agent OTP Realty",
            license_number="AGENT-OTP-001",
            payment_status=Agency.PAYMENT_PAID,
        )
        self.agent = User.objects.create_user(
            email="unverified-agent@example.com",
            password="Agent-Password-2026",
            full_name="Unverified Agent",
            agency=self.agency,
            role=User.ROLE_AGENT,
            is_email_verified=False,
        )

    def tearDown(self):
        cache.clear()

    @override_settings(REQUIRE_AGENT_OTP_VERIFICATION=False)
    @patch("users.views.send_login_verification_otp")
    def test_local_agent_login_bypasses_otp_without_marking_email_verified(self, send_otp):
        response = self.client.post(
            reverse("login"),
            {"email": self.agent.email, "password": "Agent-Password-2026"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        send_otp.assert_not_called()
        self.agent.refresh_from_db()
        self.assertFalse(self.agent.is_email_verified)

    @override_settings(REQUIRE_AGENT_OTP_VERIFICATION=True)
    @patch("users.views.send_login_verification_otp")
    def test_production_agent_login_requires_otp(self, send_otp):
        response = self.client.post(
            reverse("login"),
            {"email": self.agent.email, "password": "Agent-Password-2026"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(response.data["otp_required"])
        send_otp.assert_called_once_with(self.agent)

    @override_settings(REQUIRE_AGENT_OTP_VERIFICATION=False)
    @patch("users.views.send_login_verification_otp")
    def test_local_setting_does_not_bypass_owner_otp(self, send_otp):
        owner = User.objects.create_user(
            email="unverified-owner@example.com",
            password="Owner-Password-2026",
            full_name="Unverified Owner",
            agency=self.agency,
            role=User.ROLE_AGENCY_OWNER,
            is_email_verified=False,
        )
        response = self.client.post(
            reverse("login"),
            {"email": owner.email, "password": "Owner-Password-2026"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(response.data["otp_required"])
        send_otp.assert_called_once_with(owner)

    @override_settings(REQUIRE_AGENT_OTP_VERIFICATION=False)
    @patch("users.views.send_login_verification_otp")
    def test_local_agent_cannot_request_an_unnecessary_otp(self, send_otp):
        response = self.client.post(
            reverse("resend-login-otp"),
            {"email": self.agent.email, "password": "Agent-Password-2026"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("disabled", response.data["detail"])
        send_otp.assert_not_called()


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
            "password": "Owner-Created-Agent-2026",
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
            "password": "Manager-Created-Agent-2026",
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

    def test_owner_can_change_agent_password_using_patch(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(
            reverse("agent-detail", kwargs={"pk": self.agent.id}),
            {"password": "A-Much-Better-Password-2026"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.agent.refresh_from_db()
        self.assertTrue(self.agent.check_password("A-Much-Better-Password-2026"))


class PasswordPolicyAndResetAPITestCase(APITestCase):
    def setUp(self):
        cache.clear()
        self.agency = Agency.objects.create(
            name="Password Reset Realty",
            license_number="PASSWORD-RESET-001",
            payment_status=Agency.PAYMENT_PAID,
        )
        self.user = User.objects.create_user(
            email="reset@example.com",
            password="Original-Password-2026",
            full_name="Reset User",
            agency=self.agency,
            role=User.ROLE_AGENCY_OWNER,
            is_email_verified=True,
        )

    def tearDown(self):
        cache.clear()

    def test_registration_rejects_password_disallowed_by_django_policy(self):
        response = self.client.post(
            reverse("register"),
            {
                "full_name": "Weak Password User",
                "email": "weak@example.com",
                "password": "12345678",
                "agency_name": "Weak Password Realty",
                "license_number": "WEAK-PASSWORD-001",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

    def test_password_reset_request_does_not_reveal_account_existence(self):
        existing = self.client.post(
            reverse("password-reset"),
            {"email": self.user.email},
            format="json",
        )
        missing = self.client.post(
            reverse("password-reset"),
            {"email": "missing@example.com"},
            format="json",
        )

        self.assertEqual(existing.status_code, status.HTTP_200_OK)
        self.assertEqual(missing.status_code, status.HTTP_200_OK)
        self.assertEqual(existing.data, missing.data)
        self.assertEqual(len(mail.outbox), 1)

    @patch("users.views.send_mail", side_effect=RuntimeError("SMTP unavailable"))
    def test_password_reset_request_does_not_reveal_mail_failure(self, _send_mail):
        response = self.client.post(
            reverse("password-reset"),
            {"email": self.user.email},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("message", response.data)

    def test_password_reset_link_changes_password_and_is_single_use(self):
        request_response = self.client.post(
            reverse("password-reset"),
            {"email": self.user.email},
            format="json",
        )
        self.assertEqual(request_response.status_code, status.HTTP_200_OK)
        match = re.search(r"[?&]uid=([^&\s]+)&token=([^\s]+)", mail.outbox[0].body)
        self.assertIsNotNone(match)
        payload = {
            "uid": match.group(1),
            "token": match.group(2),
            "new_password": "Replacement-Password-2026",
        }

        response = self.client.post(
            reverse("password-reset-confirm"),
            payload,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Replacement-Password-2026"))

        reused = self.client.post(
            reverse("password-reset-confirm"),
            payload,
            format="json",
        )
        self.assertEqual(reused.status_code, status.HTTP_400_BAD_REQUEST)


class AgentProfileAPITestCase(APITestCase):
    def setUp(self):
        self.agency = Agency.objects.create(
            name="Agent Profiles Realty",
            license_number="AGENT-PROFILE-001",
            payment_status=Agency.PAYMENT_PAID,
        )
        self.other_agency = Agency.objects.create(
            name="Other Profiles Realty",
            license_number="AGENT-PROFILE-002",
            payment_status=Agency.PAYMENT_PAID,
        )
        self.agent = User.objects.create_user(
            email="profile-agent@example.com",
            password="Password123",
            full_name="Profile Agent",
            agency=self.agency,
            role=User.ROLE_AGENT,
        )
        self.owner = User.objects.create_user(
            email="profile-owner@example.com",
            password="Password123",
            full_name="Profile Owner",
            agency=self.agency,
            role=User.ROLE_AGENCY_OWNER,
        )
        self.other_agent = User.objects.create_user(
            email="other-profile-agent@example.com",
            password="Password123",
            full_name="Other Profile Agent",
            agency=self.other_agency,
            role=User.ROLE_AGENT,
        )
        self.current_property = Property.objects.create(
            agency=self.agency,
            assigned_agent=self.agent,
            title="Published Agent Listing",
            property_type="house",
            purpose="sale",
            price="25000000",
            province="Bagmati",
            district="Kathmandu",
            city="Kathmandu",
            status="available",
            is_published=True,
        )
        self.sold_property = Property.objects.create(
            agency=self.agency,
            assigned_agent=self.agent,
            title="Closed Agent Listing",
            property_type="apartment",
            purpose="sale",
            price="18000000",
            province="Bagmati",
            district="Lalitpur",
            city="Lalitpur",
            status="sold",
        )

    def test_agent_can_retrieve_and_update_own_profile(self):
        self.client.force_authenticate(user=self.agent)
        response = self.client.patch(
            reverse("agent-self-profile"),
            {
                "full_name": "Aarav Shrestha",
                "phone": "+977 9800000001",
                "designation": "Principal Broker",
                "location": "Kathmandu Valley",
                "years_experience": 14,
                "languages": [" English ", "Nepali", "english", "Hindi"],
                "specialties": ["Luxury Villas", "Negotiation"],
                "bio": "Research-led residential property advisor.",
                "linkedin_url": "https://linkedin.com/in/aarav",
                "instagram_url": "https://instagram.com/aarav",
                "facebook_url": "https://facebook.com/aarav",
                "deals_closed": 999,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["languages"], ["English", "Nepali", "Hindi"])
        self.assertEqual(response.data["deals_closed"], 1)
        self.assertEqual(
            response.data["current_listing_ids"],
            [f"LP-{self.current_property.id:03d}"],
        )
        self.assertEqual(
            response.data["sold_property_ids"],
            [f"LP-{self.sold_property.id:03d}"],
        )
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.full_name, "Aarav Shrestha")
        self.assertEqual(self.agent.years_experience, 14)

    def test_only_agents_can_use_self_profile_endpoint(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(reverse("agent-self-profile"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_invalid_profile_values_are_rejected(self):
        self.client.force_authenticate(user=self.agent)
        response = self.client.patch(
            reverse("agent-self-profile"),
            {
                "years_experience": 81,
                "languages": "English",
                "linkedin_url": "not-a-url",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_public_agent_detail_returns_profile_and_derived_property_data(self):
        self.agent.location = "Kathmandu Valley"
        self.agent.languages = ["English", "Nepali"]
        self.agent.specialties = ["Luxury Villas"]
        self.agent.years_experience = 8
        self.agent.save()

        response = self.client.get(
            reverse(
                "public-agent-detail",
                kwargs={
                    "license_number": self.agency.license_number,
                    "pk": self.agent.id,
                },
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["location"], "Kathmandu Valley")
        self.assertEqual(response.data["deals_closed"], 1)
        self.assertEqual(
            response.data["current_listing_ids"],
            [f"LP-{self.current_property.id:03d}"],
        )
        self.assertEqual(response.data["reviews"], [])
        self.assertEqual(response.data["rating"], 0)

    def test_public_agent_detail_is_agency_scoped_and_hides_inactive_agents(self):
        wrong_agency = self.client.get(
            reverse(
                "public-agent-detail",
                kwargs={
                    "license_number": self.agency.license_number,
                    "pk": self.other_agent.id,
                },
            )
        )
        self.assertEqual(wrong_agency.status_code, status.HTTP_404_NOT_FOUND)

        self.agent.is_active = False
        self.agent.save(update_fields=["is_active"])
        inactive = self.client.get(
            reverse(
                "public-agent-detail",
                kwargs={
                    "license_number": self.agency.license_number,
                    "pk": self.agent.id,
                },
            )
        )
        self.assertEqual(inactive.status_code, status.HTTP_404_NOT_FOUND)
