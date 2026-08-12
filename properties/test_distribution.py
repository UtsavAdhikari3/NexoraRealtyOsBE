import io
import zipfile
from datetime import timedelta
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from rest_framework.test import APITestCase

from agencies.models import Agency
from leads.models import Lead
from social_media.models import SocialAccount, SocialPost
from users.models import AgencyUser
from .models import Property, PropertyDistributionLink, PropertyEvent, PropertyMedia


def image_upload(name="property.jpg"):
    output = io.BytesIO()
    Image.new("RGB", (1200, 800), "#a7b8ad").save(output, "JPEG")
    return SimpleUploadedFile(name, output.getvalue(), content_type="image/jpeg")


def response_bytes(response):
    if getattr(response, "streaming", False):
        return b"".join(response.streaming_content)
    return response.content


@override_settings(
    PUBLIC_API_BASE_URL="https://go.nexora.test",
    STOREFRONT_PUBLIC_URL="https://homes.nexora.test",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class PropertyDistributionTests(APITestCase):
    def setUp(self):
        self.agency = Agency.objects.create(
            name="Nepal Home Network", license_number="DIST-001",
            payment_status="paid", primary_color="#496B5A",
            phone="9800000000", email="hello@example.com",
        )
        self.manager = AgencyUser.objects.create_user(
            email="distribution-manager@example.com", password="Password123",
            full_name="Distribution Manager", agency=self.agency,
            role=AgencyUser.ROLE_AGENCY_MANAGER,
        )
        self.agent = AgencyUser.objects.create_user(
            email="distribution-agent@example.com", password="Password123",
            full_name="Listing Agent", agency=self.agency,
            role=AgencyUser.ROLE_AGENT, phone="9811111111",
        )
        self.property = Property.objects.create(
            agency=self.agency, assigned_agent=self.agent,
            title="Modern Family House in Baneshwor", property_type="house",
            purpose="sale", price=32500000, province="Bagmati",
            district="Kathmandu", city="Kathmandu",
            municipality="Kathmandu Metropolitan City", ward_number="10",
            tole="New Baneshwor", landmark="Shankhamul Chowk",
            address="Ward 10", land_area_value=6, land_area_unit="aana",
            bedrooms=4, bathrooms=3, floors=2, road_access_value=20,
            road_access_unit="ft", road_type="blacktopped",
            facing_direction="east", description="A bright family home with parking and reliable utilities.",
            short_description="Family home with 20 ft road access.",
            status="available", is_published=True,
            availability_verified_at=timezone.now(),
            listing_expires_at=timezone.now() + timedelta(days=30),
        )
        PropertyMedia.objects.create(
            agency=self.agency, property=self.property, media_type="image",
            file=image_upload(), title="Front elevation", is_primary=True,
            uploaded_by=self.manager,
        )
        self.client.force_authenticate(self.manager)

    def test_toolkit_returns_bilingual_copy_assets_and_attribution(self):
        PropertyEvent.objects.create(
            agency=self.agency, property=self.property,
            event_type=PropertyEvent.EVENT_INQUIRY, utm_source="facebook",
        )
        response = self.client.get(reverse(
            "property-distribution-toolkit", kwargs={"property_id": self.property.id}
        ))
        self.assertEqual(response.status_code, 200)
        self.assertIn("For sale", response.data["captions"]["english"]["facebook"])
        self.assertIn("बिक्रीमा", response.data["captions"]["nepali"]["facebook"])
        self.assertEqual(len(response.data["assets"]), 9)
        self.assertEqual(response.data["attribution"][0]["inquiries"], 1)

    def test_tracked_short_link_redirects_and_records_click(self):
        create = self.client.post(reverse(
            "property-distribution-links", kwargs={"property_id": self.property.id}
        ), {"label": "Facebook launch", "source": "facebook", "medium": "social", "campaign": "dashain-homes"})
        self.assertEqual(create.status_code, 201)
        link = PropertyDistributionLink.objects.get(id=create.data["id"])
        self.client.force_authenticate(None)
        redirect_response = self.client.get(reverse("public-distribution-link", kwargs={"code": link.code}))
        self.assertEqual(redirect_response.status_code, 302, getattr(redirect_response, "data", None))
        self.assertIn("utm_source=facebook", redirect_response["Location"])
        link.refresh_from_db()
        self.assertEqual(link.click_count, 1)
        event = PropertyEvent.objects.get(event_type=PropertyEvent.EVENT_DISTRIBUTION_CLICK)
        self.assertEqual(event.utm_campaign, "dashain-homes")

    def test_image_qr_pdf_and_csv_assets_are_downloadable(self):
        cases = [
            ("facebook_post", "image/jpeg", b"\xff\xd8"),
            ("instagram_post", "image/jpeg", b"\xff\xd8"),
            ("instagram_story", "image/jpeg", b"\xff\xd8"),
            ("qr_code", "image/png", b"\x89PNG"),
            ("brochure", "application/pdf", b"%PDF"),
            ("window_card", "application/pdf", b"%PDF"),
            ("portal_csv", "text/csv", b"\xef\xbb\xbf"),
        ]
        for asset_type, content_type, signature in cases:
            with self.subTest(asset_type=asset_type):
                response = self.client.get(reverse(
                    "property-distribution-asset",
                    kwargs={"property_id": self.property.id, "asset_type": asset_type},
                ))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response["Content-Type"].startswith(content_type))
                self.assertTrue(response_bytes(response).startswith(signature))

    def test_watermarked_and_complete_media_packages_contain_expected_files(self):
        for asset_type, expected in [
            ("watermarked_images", "watermarked/01-Front-elevation.jpg"),
            ("media_package", "print/property-brochure.pdf"),
        ]:
            response = self.client.get(reverse(
                "property-distribution-asset",
                kwargs={"property_id": self.property.id, "asset_type": asset_type},
            ))
            self.assertEqual(response.status_code, 200)
            with zipfile.ZipFile(io.BytesIO(response_bytes(response))) as archive:
                self.assertIn(expected, archive.namelist())
                if asset_type == "media_package":
                    self.assertIn("social/instagram-story.jpg", archive.namelist())
                    self.assertIn("copy/nepali-captions.txt", archive.namelist())
                    self.assertIn("portal/property.csv", archive.namelist())

    def test_social_draft_uses_generated_creative_and_caption(self):
        account = SocialAccount.objects.create(
            agency=self.agency, provider="meta", platform="facebook",
            external_id="page-1", name="Nepal Home Network",
            access_token="test-token", status=SocialAccount.STATUS_CONNECTED,
            connected_by=self.manager,
        )
        with patch("social_media.services.publishing.publish_social_post") as publish_mock:
            response = self.client.post(reverse(
                "property-distribution-social-draft", kwargs={"property_id": self.property.id}
            ), {
                "social_account": account.id,
                "language": "nepali",
                # Accepted for compatibility, but publishing must happen only
                # through the dedicated social-post publish endpoint.
                "publish_now": True,
            })
        self.assertEqual(response.status_code, 201)
        post = SocialPost.objects.get(id=response.data["id"])
        self.assertEqual(post.property, self.property)
        self.assertEqual(post.status, SocialPost.STATUS_DRAFT)
        self.assertIn("बिक्रीमा", post.caption)
        self.assertIn("facebook_post", post.image.name)
        self.assertTrue(post.image.name.endswith(".jpg"))
        publish_mock.assert_not_called()

    def test_social_draft_requires_a_connected_account_id(self):
        response = self.client.post(reverse(
            "property-distribution-social-draft",
            kwargs={"property_id": self.property.id},
        ), {})

        self.assertEqual(response.status_code, 400)
        self.assertIn("social_account", response.data)

    def test_inquiry_preserves_distribution_attribution_on_lead_and_event(self):
        self.client.force_authenticate(None)
        response = self.client.post(reverse("public-property-inquiry", kwargs={
            "license_number": self.agency.license_number,
            "property_id": self.property.id,
        }), {
            "full_name": "Tracked Buyer", "phone": "9801234567",
            "message": "Interested", "utm_source": "viber",
            "utm_medium": "messaging", "utm_campaign": "kathmandu-land",
            "distribution_code": "abc123",
        })
        self.assertEqual(response.status_code, 201)
        lead = Lead.objects.get(phone="9801234567")
        self.assertEqual(
            lead.custom_data["distribution_attribution"]["utm_source"], "viber"
        )
        event = PropertyEvent.objects.get(event_type=PropertyEvent.EVENT_INQUIRY)
        self.assertEqual(event.utm_campaign, "kathmandu-land")

    def test_site_visit_preserves_distribution_attribution(self):
        self.client.force_authenticate(None)
        response = self.client.post(reverse("public-request-site-visit", kwargs={
            "license_number": self.agency.license_number,
            "property_id": self.property.id,
        }), {
            "full_name": "Tracked Visitor", "phone": "9801234599",
            "preferred_datetime": (timezone.now() + timedelta(days=2)).isoformat(),
            "utm_source": "whatsapp", "utm_medium": "messaging",
            "utm_campaign": "baneshwor-homes", "distribution_code": "visit123",
        })
        self.assertEqual(response.status_code, 201)
        event = PropertyEvent.objects.get(
            event_type=PropertyEvent.EVENT_SITE_VISIT_REQUEST
        )
        self.assertEqual(event.utm_source, "whatsapp")
        self.assertEqual(event.metadata["distribution_code"], "visit123")

    def test_portal_export_can_select_properties(self):
        response = self.client.get(reverse("property-portal-export"), {"ids": str(self.property.id)})
        body = response.content.decode("utf-8-sig")
        self.assertEqual(response.status_code, 200)
        self.assertIn("listing_id,title,purpose", body)
        self.assertIn("LP-", body)

    def test_unassigned_agent_cannot_distribute_another_agents_property(self):
        other = AgencyUser.objects.create_user(
            email="other-distribution-agent@example.com", password="Password123",
            full_name="Other Agent", agency=self.agency, role=AgencyUser.ROLE_AGENT,
        )
        self.client.force_authenticate(other)
        response = self.client.get(reverse(
            "property-distribution-toolkit", kwargs={"property_id": self.property.id}
        ))
        self.assertEqual(response.status_code, 403)

    def test_agent_portal_export_only_contains_assigned_properties(self):
        Property.objects.create(
            agency=self.agency, title="Unassigned listing", property_type="land",
            purpose="sale", price=10000000, province="Bagmati",
            district="Bhaktapur", city="Bhaktapur", status="available",
        )
        self.client.force_authenticate(self.agent)
        response = self.client.get(reverse("property-portal-export"))
        body = response.content.decode("utf-8-sig")
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.property.title, body)
        self.assertNotIn("Unassigned listing", body)
