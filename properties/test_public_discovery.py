from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from agencies.models import Agency
from properties.models import Property, PropertyMedia
from users.models import AgencyUser


class PublicPropertyDiscoveryTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.agency = Agency.objects.create(
            name="Discovery Realty",
            license_number="DISCOVERY-001",
            payment_status=Agency.PAYMENT_PAID,
            is_website_published=True,
        )
        self.other_agency = Agency.objects.create(
            name="Other Discovery Realty",
            license_number="DISCOVERY-OTHER",
            payment_status=Agency.PAYMENT_PAID,
            is_website_published=True,
        )
        self.agent = AgencyUser.objects.create_user(
            email="discovery-agent@example.com",
            password="Password123",
            agency=self.agency,
            role=AgencyUser.ROLE_AGENT,
            full_name="Discovery Agent",
        )
        self.other_agent = AgencyUser.objects.create_user(
            email="other-discovery-agent@example.com",
            password="Password123",
            agency=self.other_agency,
            role=AgencyUser.ROLE_AGENT,
            full_name="Other Agent",
        )
        self.list_url = reverse(
            "public-property-list",
            kwargs={"license_number": self.agency.license_number},
        )

    def tearDown(self):
        cache.clear()

    def make_property(self, title, **overrides):
        values = {
            "agency": self.agency,
            "title": title,
            "property_type": "house",
            "purpose": "sale",
            "price": "20000000",
            "province": "Bagmati",
            "district": "Kathmandu",
            "city": "Kathmandu",
            "municipality": "Kathmandu Metropolitan City",
            "status": "available",
            "is_published": True,
        }
        values.update(overrides)
        return Property.objects.create(**values)

    def test_list_is_paginated_and_uses_bounded_card_contract(self):
        for index in range(26):
            self.make_property(f"Listing {index:02d}")

        first = self.client.get(self.list_url)
        second = self.client.get(self.list_url, {"page": 2})

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["count"], 26)
        self.assertEqual(len(first.data["results"]), 24)
        self.assertEqual(len(second.data["results"]), 2)
        card = first.data["results"][0]
        self.assertIn("primary_image", card)
        self.assertNotIn("description", card)
        self.assertNotIn("media", card)

    def test_agent_ids_and_ordering_filters_are_tenant_safe(self):
        first = self.make_property("First", assigned_agent=self.agent, price="300")
        second = self.make_property("Second", assigned_agent=self.agent, price="100")
        self.make_property("Unassigned", price="200")

        filtered = self.client.get(self.list_url, {"assigned_agent": self.agent.id})
        cross_tenant = self.client.get(self.list_url, {"assigned_agent": self.other_agent.id})
        manual = self.client.get(self.list_url, {"ids": f"{second.id},{first.id}"})
        cheapest = self.client.get(self.list_url, {"ordering": "price_asc"})

        self.assertEqual([item["id"] for item in filtered.data["results"]], [second.id, first.id])
        self.assertEqual(cross_tenant.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual([item["id"] for item in manual.data["results"]], [second.id, first.id])
        self.assertEqual(cheapest.data["results"][0]["id"], second.id)

    def test_facets_count_only_public_inventory(self):
        self.make_property("Public House")
        self.make_property(
            "Public Land",
            property_type="land",
            purpose="rent",
            city="Pokhara",
            district="Kaski",
            municipality="Pokhara Metropolitan City",
        )
        self.make_property(
            "Hidden Apartment",
            property_type="apartment",
            city="Secret City",
            is_published=False,
        )

        response = self.client.get(reverse(
            "public-property-filter-options",
            kwargs={"license_number": self.agency.license_number},
        ))

        self.assertEqual(response.data["summary"]["total"], 2)
        self.assertEqual(response.data["summary"]["sale"], 1)
        self.assertEqual(response.data["summary"]["rent"], 1)
        self.assertEqual(
            {item["value"]: item["count"] for item in response.data["property_types"]},
            {"house": 1, "land": 1},
        )
        self.assertNotIn("Secret City", [item["value"] for item in response.data["locations"]["cities"]])

    def test_similar_ranking_prefers_strong_type_and_purpose_match(self):
        current = self.make_property("Current", bedrooms=3)
        strong = self.make_property("Strong", bedrooms=4, price="22000000")
        weak = self.make_property(
            "Weak",
            property_type="land",
            purpose="rent",
            price="21000000",
        )

        response = self.client.get(reverse(
            "public-similar-properties",
            kwargs={"license_number": self.agency.license_number, "property_id": current.id},
        ))

        ids = [item["id"] for item in response.data["results"]]
        self.assertEqual(ids[0], strong.id)
        self.assertIn(weak.id, ids)

    def test_detail_exposes_only_ordered_public_page_media(self):
        property_obj = self.make_property("Media listing")
        public_image = PropertyMedia.objects.create(
            agency=self.agency,
            property=property_obj,
            media_type="image",
            external_url="https://example.com/public.jpg",
            is_primary=True,
            sort_order=8,
            alt_text="Front elevation",
        )
        PropertyMedia.objects.create(
            agency=self.agency,
            property=property_obj,
            media_type="image",
            external_url="https://example.com/hidden.jpg",
            is_public=False,
        )
        PropertyMedia.objects.create(
            agency=self.agency,
            property=property_obj,
            media_type="document",
            external_url="https://example.com/private-document.pdf",
        )

        response = self.client.get(reverse(
            "public-property-detail",
            kwargs={"license_number": self.agency.license_number, "pk": property_obj.id},
        ))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in response.data["media"]], [public_image.id])
        self.assertEqual(response.data["media"][0]["alt_text"], "Front elevation")

    def test_rental_period_and_public_privacy_preferences_are_enforced(self):
        self.agent.show_phone_publicly = False
        self.agent.show_email_publicly = False
        self.agent.save(update_fields=["show_phone_publicly", "show_email_publicly"])
        property_obj = self.make_property(
            "Private-location rental",
            purpose="rent",
            rent_period="month",
            assigned_agent=self.agent,
            show_exact_location_publicly=False,
            address="House 4, private lane",
            tole="Private Tole",
            neighbourhood="Private Neighbourhood",
            ward_number="4",
            landmark="Private landmark",
            latitude="27.7172",
            longitude="85.3240",
        )

        detail = self.client.get(reverse(
            "public-property-detail",
            kwargs={"license_number": self.agency.license_number, "pk": property_obj.id},
        ))
        card = self.client.get(self.list_url, {"ids": property_obj.id}).data["results"][0]
        agent = self.client.get(reverse(
            "public-agent-detail",
            kwargs={"license_number": self.agency.license_number, "pk": self.agent.id},
        ))

        self.assertEqual(detail.data["rent_period"], "month")
        for field in ("address", "tole", "neighbourhood", "ward_number", "landmark"):
            self.assertEqual(detail.data[field], "")
        self.assertIsNone(detail.data["latitude"])
        self.assertIsNone(card["longitude"])
        self.assertIsNone(detail.data["assigned_agent_detail"]["phone"])
        self.assertIsNone(detail.data["assigned_agent_detail"]["email"])
        self.assertIsNone(agent.data["phone"])
        self.assertIsNone(agent.data["email"])
