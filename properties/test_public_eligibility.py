from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

from agencies.models import Agency
from operations.models import PublicSubmission
from properties.models import Property, PropertyDistributionLink


class PublicWebsiteEligibilityTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.agency = Agency.objects.create(
            name="Visible Realty",
            license_number="VISIBLE-001",
            slug="visible-realty",
            payment_status=Agency.PAYMENT_PAID,
            is_website_published=True,
        )
        self.other_agency = Agency.objects.create(
            name="Other Realty",
            license_number="OTHER-ELIG-001",
            slug="other-eligibility",
            payment_status=Agency.PAYMENT_PAID,
            is_website_published=True,
        )
        self.property = self.make_property(self.agency, "Visible House")
        self.other_property = self.make_property(self.other_agency, "Other House")

    def tearDown(self):
        cache.clear()

    def make_property(self, agency, title, **overrides):
        values = {
            "agency": agency,
            "title": title,
            "property_type": "house",
            "purpose": "sale",
            "price": "25000000",
            "province": "Bagmati",
            "district": "Kathmandu",
            "city": "Kathmandu",
            "status": "available",
            "is_published": True,
        }
        values.update(overrides)
        return Property.objects.create(**values)

    def public_urls(self):
        return [
            reverse("public-property-list", kwargs={"license_number": self.agency.license_number}),
            reverse("public-property-detail", kwargs={"license_number": self.agency.license_number, "pk": self.property.pk}),
            reverse("public-property-share-detail", kwargs={"slug": self.agency.slug, "share_slug": self.property.share_slug}),
            reverse("public-similar-properties", kwargs={"license_number": self.agency.license_number, "property_id": self.property.pk}),
        ]

    def test_unpublished_website_hides_all_property_read_paths(self):
        self.agency.is_website_published = False
        self.agency.save(update_fields=["is_website_published"])

        for url in self.public_urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)

    def test_expired_subscription_hides_share_and_alternate_paths(self):
        self.agency.subscription_expires_at = timezone.now() - timedelta(minutes=1)
        self.agency.save(update_fields=["subscription_expires_at"])
        link = PropertyDistributionLink.objects.create(
            agency=self.agency,
            property=self.property,
            source="email",
        )

        share = reverse(
            "public-property-share-detail",
            kwargs={"slug": self.agency.slug, "share_slug": self.property.share_slug},
        )
        redirect_url = reverse("public-distribution-link", kwargs={"code": link.code})
        self.assertEqual(self.client.get(share).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.get(redirect_url).status_code, status.HTTP_404_NOT_FOUND)

    def test_similar_results_are_same_agency_and_publicly_eligible(self):
        relevant = self.make_property(self.agency, "Nearby House", price="26000000")
        stale = self.make_property(self.agency, "Stale House")
        Property.objects.filter(pk=stale.pk).update(
            listing_expires_at=timezone.now() - timedelta(minutes=1),
            is_published=True,
        )

        response = self.client.get(reverse(
            "public-similar-properties",
            kwargs={"license_number": self.agency.license_number, "property_id": self.property.pk},
        ))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item["id"] for item in response.data["results"]}
        self.assertIn(relevant.pk, ids)
        self.assertNotIn(stale.pk, ids)
        self.assertNotIn(self.other_property.pk, ids)
        self.assertNotIn(self.property.pk, ids)

    def test_site_visit_rejects_stale_property(self):
        Property.objects.filter(pk=self.property.pk).update(
            listing_expires_at=timezone.now() - timedelta(minutes=1),
            is_published=True,
        )
        response = self.client.post(
            reverse("public-request-site-visit", kwargs={
                "license_number": self.agency.license_number,
                "property_id": self.property.pk,
            }),
            {
                "full_name": "Visitor",
                "phone": "9800000000",
                "preferred_datetime": (timezone.now() + timedelta(days=1)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_generic_submission_rejects_hidden_and_cross_tenant_properties(self):
        hidden = self.make_property(
            self.agency,
            "Hidden House",
            status="hidden",
            is_published=False,
        )
        url = reverse("public-submission-create", kwargs={"slug": self.agency.slug})
        base = {
            "kind": "listing_report",
            "message": "This listing needs review.",
            "metadata": {"reason": "already_sold"},
        }

        hidden_response = self.client.post(url, {**base, "property": hidden.pk}, format="json")
        cross_response = self.client.post(url, {**base, "property": self.other_property.pk}, format="json")

        self.assertEqual(hidden_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(cross_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(PublicSubmission.objects.exists())
