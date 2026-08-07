from decimal import Decimal

from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from agencies.models import Agency
from .models import Property

from .area import conversion_payload, convert_area, price_per_area


class NepalAreaConversionTests(SimpleTestCase):
    def test_hill_units(self):
        self.assertEqual(convert_area(1, "ropani", "aana"), Decimal("16"))
        self.assertEqual(convert_area(1, "aana", "paisa"), Decimal("4"))
        self.assertEqual(convert_area(1, "paisa", "daam"), Decimal("4"))

    def test_terai_units(self):
        self.assertEqual(convert_area(1, "bigha", "kattha"), Decimal("20"))
        self.assertEqual(convert_area(1, "kattha", "dhur"), Decimal("20"))

    def test_metric_and_square_feet(self):
        self.assertEqual(convert_area(1, "sqft", "sqft"), Decimal("1"))
        self.assertAlmostEqual(float(convert_area(1, "sqm", "sqft")), 10.7639104167)

    def test_conversion_payload_and_price_rate(self):
        payload = conversion_payload(1, "ropani")
        self.assertEqual(payload["aana"], "16.0000")
        self.assertEqual(price_per_area(16000000, 1, "ropani", "aana"), "1000000.00")


class NepalPropertyPublicAPITests(APITestCase):
    def setUp(self):
        self.agency = Agency.objects.create(
            name="Nepal Land Realty", license_number="NP-AREA-001", payment_status="paid"
        )
        common = {
            "agency": self.agency, "property_type": "land", "purpose": "sale",
            "price": 16000000, "province": "Bagmati", "district": "Kathmandu",
            "city": "Kathmandu", "municipality": "Kageshwori Manohara",
            "ward_number": "9", "tole": "Gothatar", "landmark": "Tej Binayak Chowk",
            "status": "available", "is_published": True,
        }
        self.ropani = Property.objects.create(
            **common, title="One Ropani Plot", land_area_value=1, land_area_unit="ropani",
            land_use_classification="residential", road_type="blacktopped",
        )
        self.small = Property.objects.create(
            **common, title="Ten Aana Plot", land_area_value=10, land_area_unit="aana",
        )

    def test_cross_unit_area_filter_uses_canonical_area(self):
        response = self.client.get(
            reverse("public-property-list", kwargs={"license_number": self.agency.license_number}),
            {"land_area_min": "15", "land_area_unit": "aana"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.data], [self.ropani.id])

    def test_public_payload_exposes_nepal_fields_and_rates(self):
        response = self.client.get(
            reverse("public-property-detail", kwargs={
                "license_number": self.agency.license_number, "pk": self.ropani.id,
            })
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["land_area_conversions"]["aana"], "16.0000")
        self.assertEqual(response.data["price_per_aana"], "1000000.00")
        self.assertEqual(response.data["municipality"], "Kageshwori Manohara")
