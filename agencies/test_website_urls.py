from types import SimpleNamespace

from django.test import SimpleTestCase, override_settings

from .website_urls import add_url_query, agency_website_url, property_website_url


class WebsiteUrlTests(SimpleTestCase):
    @override_settings(STOREFRONT_PUBLIC_URL="http://localhost:5173/?tenant={slug}")
    def test_local_agency_and_property_urls_keep_tenant_query(self):
        agency = SimpleNamespace(slug="nepal-bhoomi-nr-123")
        property_obj = SimpleNamespace(
            id=8,
            title="Family Home",
            share_slug="family-home-abc123",
            agency=agency,
        )

        self.assertEqual(
            agency_website_url(agency),
            "http://localhost:5173/?tenant=nepal-bhoomi-nr-123",
        )
        self.assertEqual(
            property_website_url(property_obj),
            "http://localhost:5173/properties/family-home-abc123?tenant=nepal-bhoomi-nr-123",
        )

    @override_settings(STOREFRONT_PUBLIC_URL="https://{slug}.nexorarealtyos.com")
    def test_production_pattern_uses_agency_subdomain(self):
        agency = SimpleNamespace(slug="nepal-bhoomi-nr-123")
        self.assertEqual(
            agency_website_url(agency),
            "https://nepal-bhoomi-nr-123.nexorarealtyos.com",
        )

    def test_tracking_query_merges_with_existing_tenant(self):
        result = add_url_query(
            "http://localhost:5173/properties/home?tenant=nepal-bhoomi-nr-123",
            {"utm_source": "facebook", "nexora_link": "abc123", "utm_medium": ""},
        )
        self.assertEqual(
            result,
            "http://localhost:5173/properties/home?tenant=nepal-bhoomi-nr-123&utm_source=facebook&nexora_link=abc123",
        )

    @override_settings(STOREFRONT_PUBLIC_URL="https://legacy.example.com")
    def test_explicit_legacy_base_remains_compatible(self):
        self.assertEqual(
            agency_website_url("agency-one"),
            "https://legacy.example.com/agency/agency-one",
        )
