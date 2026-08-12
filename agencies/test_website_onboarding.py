from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from agencies.models import Agency
from agencies.website_onboarding import default_website_config
from users.models import AgencyUser


class WebsiteOnboardingAPITestCase(APITestCase):
    def setUp(self):
        self.agency = Agency.objects.create(
            name="Onboarding Realty",
            license_number="ONBOARD-001",
            payment_status=Agency.PAYMENT_PAID,
            is_website_published=False,
            website_draft_config=default_website_config(),
        )
        self.owner = AgencyUser.objects.create_user(
            email="onboarding-owner@example.com",
            password="Password123",
            full_name="Onboarding Owner",
            agency=self.agency,
            role=AgencyUser.ROLE_AGENCY_OWNER,
            is_email_verified=True,
        )
        self.agent = AgencyUser.objects.create_user(
            email="onboarding-agent@example.com",
            password="Password123",
            full_name="Onboarding Agent",
            agency=self.agency,
            role=AgencyUser.ROLE_AGENT,
        )

    def complete_required_profile(self):
        self.agency.email = "hello@onboarding.test"
        self.agency.phone = "+977 9800000000"
        self.agency.about = "A trusted real estate agency serving buyers and property owners across Kathmandu."
        self.agency.address = "Kathmandu, Nepal"
        self.agency.primary_color = "#496B5A"
        self.agency.logo = "agency_branding/logos/logo.png"
        self.agency.cover_image = "agency_branding/covers/cover.jpg"
        self.agency.seo_title = "Onboarding Realty Nepal"
        self.agency.seo_description = "Discover verified properties and dependable real estate guidance from our experienced Kathmandu agency team."
        self.agency.save()

    def test_owner_can_save_a_valid_draft(self):
        self.client.force_authenticate(self.owner)
        config = default_website_config()
        config["hero_title"] = "Properties selected for your next chapter"
        response = self.client.patch(
            reverse("website-onboarding"),
            {
                "phone": "+977 9800000000",
                "website_onboarding_step": 4,
                "website_draft_config": config,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.agency.refresh_from_db()
        self.assertEqual(self.agency.website_onboarding_status, Agency.WEBSITE_ONBOARDING_IN_PROGRESS)
        self.assertEqual(self.agency.website_onboarding_step, 4)
        self.assertFalse(self.agency.is_website_published)
        self.assertEqual(self.agency.website_draft_config["hero_title"], config["hero_title"])

    def test_login_directs_incomplete_owner_to_website_creator(self):
        response = self.client.post(
            reverse("login"),
            {"email": self.owner.email, "password": "Password123"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["next_route"], "/onboarding/website")

    def test_publish_rejects_incomplete_website(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(reverse("website-publish"))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("logo", response.data["missing_fields"])
        self.assertFalse(response.data["is_ready_to_publish"])

    def test_publish_copies_draft_and_makes_site_public(self):
        self.complete_required_profile()
        config = default_website_config()
        config["hero_title"] = "A better way to find property in Nepal"
        self.agency.website_draft_config = config
        self.agency.save(update_fields=["website_draft_config"])
        self.client.force_authenticate(self.owner)

        response = self.client.post(reverse("website-publish"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.agency.refresh_from_db()
        self.assertTrue(self.agency.is_website_published)
        self.assertEqual(self.agency.website_config, config)
        self.assertEqual(self.agency.website_onboarding_status, Agency.WEBSITE_ONBOARDING_COMPLETED)

        public = self.client.get(
            reverse("public-agency-detail-by-slug", kwargs={"slug": self.agency.slug})
        )
        self.assertEqual(public.status_code, status.HTTP_200_OK)
        self.assertEqual(public.data["website_config"]["hero_title"], config["hero_title"])

    def test_saving_a_new_draft_does_not_change_the_live_configuration(self):
        self.complete_required_profile()
        published = default_website_config()
        published["hero_title"] = "The currently published headline"
        self.agency.website_config = published
        self.agency.is_website_published = True
        self.agency.save(update_fields=["website_config", "is_website_published"])
        self.client.force_authenticate(self.owner)

        draft = default_website_config()
        draft["hero_title"] = "A future homepage headline"
        response = self.client.patch(
            reverse("website-onboarding"),
            {"website_draft_config": draft},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.agency.refresh_from_db()
        self.assertEqual(self.agency.website_config["hero_title"], published["hero_title"])
        self.assertEqual(self.agency.website_draft_config["hero_title"], draft["hero_title"])

    def test_unpublish_makes_the_agency_site_private_without_losing_content(self):
        self.complete_required_profile()
        self.agency.website_config = default_website_config()
        self.agency.website_draft_config = default_website_config()
        self.agency.is_website_published = True
        self.agency.save(update_fields=["website_config", "website_draft_config", "is_website_published"])
        self.client.force_authenticate(self.owner)

        response = self.client.post(reverse("website-unpublish"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.agency.refresh_from_db()
        self.assertFalse(self.agency.is_website_published)
        self.assertTrue(self.agency.website_draft_config["hero_title"])
        public = self.client.get(
            reverse("public-agency-detail-by-slug", kwargs={"slug": self.agency.slug})
        )
        self.assertEqual(public.status_code, status.HTTP_404_NOT_FOUND)

    def test_unpaid_agency_cannot_publish(self):
        self.complete_required_profile()
        self.agency.payment_status = Agency.PAYMENT_PENDING
        self.agency.save(update_fields=["payment_status"])
        self.client.force_authenticate(self.owner)

        response = self.client.post(reverse("website-publish"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(response.data.get("is_website_published", False))

    def test_agent_cannot_manage_website_onboarding(self):
        self.client.force_authenticate(self.agent)
        self.assertEqual(
            self.client.get(reverse("website-onboarding")).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_signed_preview_returns_draft_for_unpublished_agency(self):
        self.client.force_authenticate(self.owner)
        onboarding = self.client.get(reverse("website-onboarding"))
        token = onboarding.data["preview_url"].rsplit("/", 1)[-1]
        self.client.force_authenticate(user=None)
        preview = self.client.get(reverse("public-agency-website-preview"), {"token": token})
        self.assertEqual(preview.status_code, status.HTTP_200_OK)
        self.assertEqual(
            preview.data["website_config"]["hero_title"],
            self.agency.website_draft_config["hero_title"],
        )

    def test_invalid_preview_token_is_rejected(self):
        response = self.client.get(reverse("public-agency-website-preview"), {"token": "invalid"})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class WebsiteRegistrationDefaultsAPITestCase(APITestCase):
    def test_registration_creates_an_unpublished_website_draft(self):
        response = self.client.post(
            reverse("register"),
            {
                "full_name": "New Website Owner",
                "email": "new-website@example.com",
                "password": "New-Website-Password-2026",
                "agency_name": "New Website Realty",
                "license_number": "NEW-WEBSITE-001",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        agency = Agency.objects.get(license_number="NEW-WEBSITE-001")
        self.assertFalse(agency.is_website_published)
        self.assertEqual(agency.website_onboarding_status, Agency.WEBSITE_ONBOARDING_NOT_STARTED)
        self.assertTrue(agency.website_draft_config["hero_title"])
        self.assertEqual(response.data["next_step"], "payment")
