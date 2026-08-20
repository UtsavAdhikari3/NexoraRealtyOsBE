from io import BytesIO
from unittest.mock import patch

from django.urls import reverse
from django.conf import settings
from django.core import signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.storage import default_storage
from django.utils import timezone
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from agencies.models import Agency, WebsiteVersion
from agencies.website_onboarding import default_website_config
from properties.models import Property
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

    def test_autosave_merges_nested_changes_and_increments_revision(self):
        self.client.force_authenticate(self.owner)
        original = default_website_config()
        original["hero_title"] = "Original headline"
        original["section_visibility"]["about"] = True
        self.agency.website_draft_config = original
        self.agency.save(update_fields=["website_draft_config"])

        response = self.client.patch(
            reverse("website-onboarding"),
            {
                "base_revision": 0,
                "changes": {
                    "website_draft_config": {
                        "hero_title": "Autosaved headline",
                        "section_visibility": {"hero": False},
                        "section_order": ["hero", "contact_cta"],
                    }
                },
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["website_draft_revision"], 1)
        self.assertEqual(response.data["website_draft_config"]["hero_title"], "Autosaved headline")
        self.assertFalse(response.data["website_draft_config"]["section_visibility"]["hero"])
        self.assertTrue(response.data["website_draft_config"]["section_visibility"]["about"])
        self.assertEqual(response.data["website_draft_config"]["section_order"], ["hero", "contact_cta"])
        self.agency.refresh_from_db()
        self.assertEqual(self.agency.website_draft_updated_by, self.owner)
        self.assertIsNotNone(self.agency.website_draft_updated_at)

    def test_consecutive_autosaves_replace_old_form_values(self):
        self.client.force_authenticate(self.owner)
        original = default_website_config()
        original.update({
            "hero_title": "Old headline",
            "about": "Old agency description that is deliberately long enough for validation.",
            "public_phone": "+977 9800000000",
        })
        self.agency.website_draft_config = original
        self.agency.about = original["about"]
        self.agency.phone = original["public_phone"]
        self.agency.save(update_fields=["website_draft_config", "about", "phone"])

        first = self.client.patch(
            reverse("website-onboarding"),
            {
                "base_revision": 0,
                "changes": {
                    "about": "First replacement description that remains long enough for validation.",
                    "website_draft_config": {
                        "hero_title": "First replacement headline",
                        "about": "First replacement description that remains long enough for validation.",
                    },
                },
            },
            format="json",
        )
        second = self.client.patch(
            reverse("website-onboarding"),
            {
                "base_revision": first.data["website_draft_revision"],
                "changes": {
                    "about": "Newest replacement description that remains long enough for validation.",
                    "website_draft_config": {
                        "hero_title": "Newest replacement headline",
                        "about": "Newest replacement description that remains long enough for validation.",
                    },
                },
            },
            format="json",
        )

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(second.data["website_draft_config"]["hero_title"], "Newest replacement headline")
        self.assertEqual(
            second.data["website_draft_config"]["about"],
            "Newest replacement description that remains long enough for validation.",
        )
        self.agency.refresh_from_db()
        self.assertEqual(self.agency.website_draft_config["hero_title"], "Newest replacement headline")

    def test_stale_autosave_returns_conflict_without_overwriting(self):
        self.client.force_authenticate(self.owner)
        first = self.client.patch(
            reverse("website-onboarding"),
            {"base_revision": 0, "changes": {"website_draft_config": {"hero_title": "First writer"}}},
            format="json",
        )
        stale = self.client.patch(
            reverse("website-onboarding"),
            {"base_revision": 0, "changes": {"website_draft_config": {"hero_title": "Stale writer"}}},
            format="json",
        )

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(stale.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(stale.data["current_revision"], 1)
        self.assertEqual(stale.data["current"]["website_draft_config"]["hero_title"], "First writer")
        self.agency.refresh_from_db()
        self.assertEqual(self.agency.website_draft_config["hero_title"], "First writer")

    def test_editor_payload_includes_public_tenant_identity(self):
        self.client.force_authenticate(self.owner)
        response = self.client.get(reverse("website-onboarding"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["license_number"], "ONBOARD-001")
        self.assertEqual(response.data["slug"], self.agency.slug)
        self.assertEqual(response.data["template_capabilities"]["template_key"], "luxury-agency")
        self.assertEqual(
            response.data["template_capabilities"]["supported_pages"],
            ["home", "properties", "agents", "about", "contact", "valuation"],
        )

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

    def test_publish_rejects_page_the_selected_template_cannot_render(self):
        self.complete_required_profile()
        config = default_website_config()
        config["hero_title"] = "A better way to find property in Nepal"
        config["accuracy_confirmed"] = True
        config["enabled_pages"]["services"] = True
        self.agency.website_draft_config = config
        self.agency.save(update_fields=["website_draft_config"])
        self.client.force_authenticate(self.owner)

        response = self.client.post(reverse("website-publish"))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("template_capabilities", response.data["missing_fields"])
        self.assertIn("services", response.data["capability_errors"]["enabled_pages"])

    def test_navigation_cannot_reference_a_disabled_or_removed_page(self):
        self.client.force_authenticate(self.owner)
        config = default_website_config()
        config["navigation"] = [
            {"page": "services", "label": "Services", "url": "/services"}
        ]
        disabled = self.client.patch(
            reverse("website-onboarding"),
            {"website_draft_config": config},
            format="json",
        )
        self.assertEqual(disabled.status_code, status.HTTP_400_BAD_REQUEST)

        config = default_website_config()
        config["navigation"] = [
            {"page": "portal", "label": "Portal", "url": "/portal"}
        ]
        legacy = self.client.patch(
            reverse("website-onboarding"),
            {"website_draft_config": config},
            format="json",
        )
        self.assertEqual(legacy.status_code, status.HTTP_200_OK)
        self.assertEqual(legacy.data["website_draft_config"]["navigation"], [])

    def test_publish_copies_draft_and_makes_site_public(self):
        self.complete_required_profile()
        config = default_website_config()
        config["hero_title"] = "A better way to find property in Nepal"
        config["accuracy_confirmed"] = True
        self.agency.website_draft_config = config
        self.agency.save(update_fields=["website_draft_config"])
        self.client.force_authenticate(self.owner)

        response = self.client.post(reverse("website-publish"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.agency.refresh_from_db()
        self.assertTrue(self.agency.is_website_published)
        self.assertEqual(self.agency.website_published_config["hero_title"], config["hero_title"])
        self.assertEqual(self.agency.website_config, self.agency.website_published_config)
        self.assertEqual(self.agency.website_config_version, 1)
        self.assertEqual(WebsiteVersion.objects.filter(agency=self.agency).count(), 1)
        self.assertEqual(WebsiteVersion.objects.get(agency=self.agency).config["hero_title"], config["hero_title"])
        self.assertEqual(self.agency.website_onboarding_status, Agency.WEBSITE_ONBOARDING_COMPLETED)

        public = self.client.get(
            reverse("public-agency-detail-by-slug", kwargs={"slug": self.agency.slug})
        )
        self.assertEqual(public.status_code, status.HTTP_200_OK)
        self.assertEqual(public.data["website_config"]["hero_title"], config["hero_title"])

    def test_publish_history_and_restore_create_immutable_new_versions(self):
        self.complete_required_profile()
        first_config = default_website_config()
        first_config.update({"hero_title": "Version one", "accuracy_confirmed": True})
        self.agency.website_draft_config = first_config
        self.agency.save(update_fields=["website_draft_config"])
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.post(reverse("website-publish")).status_code, status.HTTP_200_OK)

        second_config = default_website_config()
        second_config.update({"hero_title": "Version two", "accuracy_confirmed": True})
        self.agency.website_draft_config = second_config
        self.agency.save(update_fields=["website_draft_config"])
        self.assertEqual(self.client.post(reverse("website-publish")).status_code, status.HTTP_200_OK)

        versions = self.client.get(reverse("website-version-list"))
        detail = self.client.get(reverse("website-version-detail", kwargs={"version": 1}))
        restored = self.client.post(reverse("website-version-restore", kwargs={"version": 1}))

        self.assertEqual([item["version"] for item in versions.data], [2, 1])
        self.assertEqual(detail.data["config"]["hero_title"], "Version one")
        self.assertEqual(restored.status_code, status.HTTP_201_CREATED)
        self.assertEqual(restored.data["version"]["version"], 3)
        self.assertEqual(restored.data["version"]["restored_from_version"], 1)
        self.agency.refresh_from_db()
        self.assertEqual(self.agency.website_published_config["hero_title"], "Version one")
        self.assertEqual(WebsiteVersion.objects.get(agency=self.agency, version=2).config["hero_title"], "Version two")

    def test_saving_a_new_draft_does_not_change_the_live_configuration(self):
        self.complete_required_profile()
        published = default_website_config()
        published["hero_title"] = "The currently published headline"
        self.agency.website_config = published
        self.agency.website_published_config = published
        self.agency.is_website_published = True
        self.agency.save(update_fields=["website_config", "website_published_config", "is_website_published"])
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
        self.assertEqual(self.agency.website_draft_config["schema_version"], 2)
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

    def test_expired_preview_token_is_rejected(self):
        with patch("agencies.public_views.signing.loads", side_effect=signing.SignatureExpired):
            response = self.client.get(reverse("public-agency-website-preview"), {"token": "expired"})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_media_upload_validates_image_and_uses_tenant_storage(self):
        self.client.force_authenticate(self.owner)
        buffer = BytesIO()
        Image.new("RGB", (96, 96), "#496B5A").save(buffer, format="PNG")
        upload = SimpleUploadedFile("unsafe agency logo.png", buffer.getvalue(), content_type="image/png")

        response = self.client.post(
            reverse("website-onboarding-media"),
            {"kind": "logo", "file": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        path = response.data["website_draft_config"]["media"]["logo"]
        self.assertTrue(path.startswith(f"agency_websites/{self.agency.id}/logo/"))
        self.assertNotIn("unsafe agency logo", path)
        self.assertTrue(response.data["media_urls"]["logo"].startswith(settings.PUBLIC_API_BASE_URL))
        default_storage.delete(path)

    def test_media_upload_rejects_spoofed_non_image(self):
        self.client.force_authenticate(self.owner)
        upload = SimpleUploadedFile("not-an-image.png", b"not really a png", content_type="image/png")
        response = self.client.post(
            reverse("website-onboarding-media"),
            {"kind": "logo", "file": upload},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("file", response.data)

    def test_public_api_returns_only_published_branding_socials_and_absolute_media(self):
        published = default_website_config()
        published.update({
            "hero_title": "Published headline",
            "primary_color": "#112233",
            "facebook_url": "https://facebook.com/published-agency",
            "instagram_url": "https://instagram.com/published-agency",
        })
        published["media"]["logo"] = "agency_websites/1/logo/published.png"
        draft = {**published, "hero_title": "Secret draft headline", "facebook_url": "https://facebook.com/draft-only"}
        self.agency.website_published_config = published
        self.agency.website_config = published
        self.agency.website_draft_config = draft
        self.agency.is_website_published = True
        self.agency.save(update_fields=["website_published_config", "website_config", "website_draft_config", "is_website_published"])

        response = self.client.get(reverse("public-agency-detail-by-slug", kwargs={"slug": self.agency.slug}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["website_config"]["hero_title"], "Published headline")
        self.assertEqual(response.data["facebook_url"], "https://facebook.com/published-agency")
        self.assertEqual(response.data["primary_color"], "#112233")
        self.assertTrue(response.data["logo"].startswith(f"{settings.PUBLIC_API_BASE_URL.rstrip('/')}/media/"))
        self.assertNotContains(response, "Secret draft headline")

    def test_two_public_agencies_never_share_brand_or_social_configuration(self):
        first = default_website_config()
        first.update({"hero_title": "First agency", "primary_color": "#112233", "facebook_url": "https://facebook.com/first"})
        second = default_website_config()
        second.update({"hero_title": "Second agency", "primary_color": "#AABBCC", "facebook_url": "https://facebook.com/second"})
        self.agency.website_published_config = first
        self.agency.is_website_published = True
        self.agency.save(update_fields=["website_published_config", "is_website_published"])
        other = Agency.objects.create(name="Other Realty", license_number="OTHER-002", slug="other-realty", payment_status=Agency.PAYMENT_PAID, is_website_published=True, website_published_config=second)

        first_response = self.client.get(reverse("public-agency-detail-by-slug", kwargs={"slug": self.agency.slug}))
        second_response = self.client.get(reverse("public-agency-detail-by-slug", kwargs={"slug": other.slug}))

        self.assertEqual(first_response.data["website_config"]["hero_title"], "First agency")
        self.assertEqual(second_response.data["website_config"]["hero_title"], "Second agency")
        self.assertNotEqual(first_response.data["facebook_url"], second_response.data["facebook_url"])

    def test_unknown_and_unowned_website_configuration_is_rejected(self):
        self.client.force_authenticate(self.owner)
        config = default_website_config()
        config["unsupported_script"] = "<script>alert(1)</script>"
        response = self.client.patch(reverse("website-onboarding"), {"website_draft_config": config}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        config = default_website_config()
        config["media"]["logo"] = "agency_websites/999/logo/stolen.png"
        response = self.client.patch(reverse("website-onboarding"), {"website_draft_config": config}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_manual_featured_properties_are_tenant_scoped_and_current(self):
        eligible = Property.objects.create(
            agency=self.agency,
            assigned_agent=self.agent,
            title="Current public home",
            property_type="house",
            purpose="sale",
            price=12000000,
            province="Bagmati",
            district="Kathmandu",
            city="Kathmandu",
            status="available",
            is_published=True,
        )
        other_agency = Agency.objects.create(name="Other listings", license_number="OTHER-LISTINGS")
        other = Property.objects.create(
            agency=other_agency,
            title="Another agency home",
            property_type="house",
            purpose="sale",
            price=10000000,
            province="Bagmati",
            district="Kathmandu",
            city="Kathmandu",
            status="available",
            is_published=True,
        )
        self.client.force_authenticate(self.owner)
        config = default_website_config()
        config.update({"featured_property_mode": "manual", "featured_property_ids": [eligible.id]})
        valid = self.client.patch(reverse("website-onboarding"), {"website_draft_config": config}, format="json")
        self.assertEqual(valid.status_code, status.HTTP_200_OK)
        self.assertEqual(valid.data["website_draft_config"]["featured_property_ids"], [eligible.id])

        config["featured_property_ids"] = [other.id]
        cross_tenant = self.client.patch(reverse("website-onboarding"), {"website_draft_config": config}, format="json")
        self.assertEqual(cross_tenant.status_code, status.HTTP_400_BAD_REQUEST)

        Property.objects.filter(pk=eligible.pk).update(listing_expires_at=timezone.now())
        config["featured_property_ids"] = [eligible.id]
        expired = self.client.patch(reverse("website-onboarding"), {"website_draft_config": config}, format="json")
        self.assertEqual(expired.status_code, status.HTTP_400_BAD_REQUEST)

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
        self.assertEqual(agency.website_draft_config["schema_version"], 2)
        self.assertEqual(response.data["next_step"], "payment")
