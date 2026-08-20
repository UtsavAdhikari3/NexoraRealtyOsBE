from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from agencies.models import Agency, AgencyDomain
from agencies.website_onboarding import default_website_config
from properties.models import Property


class PublicWebsiteSEOTests(APITestCase):
    def setUp(self):
        config = default_website_config()
        config["enabled_pages"]["about"] = True
        self.agency = Agency.objects.create(
            name="SEO Realty",
            license_number="SEO-001",
            payment_status=Agency.PAYMENT_PAID,
            is_website_published=True,
            website_published_config=config,
            website_config_version=7,
        )
        AgencyDomain.objects.create(
            agency=self.agency,
            domain="seo.example.com",
            status=AgencyDomain.STATUS_VERIFIED,
            is_active=True,
            is_primary=True,
        )
        self.visible = Property.objects.create(
            agency=self.agency, title="Visible Home", property_type="house", purpose="sale",
            price="1000000", status="available", is_published=True,
        )
        self.hidden = Property.objects.create(
            agency=self.agency, title="Hidden Home", property_type="house", purpose="sale",
            price="1000000", status="available", is_published=False,
        )

    def test_sitemap_uses_canonical_urls_and_public_selector(self):
        response = self.client.get(reverse("public-agency-sitemap", kwargs={"license_number": self.agency.license_number}))
        body = response.content.decode()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("https://seo.example.com/about", body)
        self.assertIn(self.visible.share_slug, body)
        self.assertNotIn(self.hidden.title, body)

    def test_robots_points_to_canonical_sitemap(self):
        response = self.client.get(reverse("public-agency-robots", kwargs={"license_number": self.agency.license_number}))
        self.assertContains(response, "Allow: /")
        self.assertContains(response, "https://seo.example.com/sitemap.xml")

    def test_public_bootstrap_supports_conditional_etag(self):
        url = reverse("public-agency-detail-by-slug", kwargs={"slug": self.agency.slug})
        first = self.client.get(url)
        second = self.client.get(url, HTTP_IF_NONE_MATCH=first["ETag"])
        self.assertEqual(first["ETag"], f'"agency-{self.agency.pk}-v7"')
        self.assertEqual(second.status_code, status.HTTP_304_NOT_MODIFIED)
