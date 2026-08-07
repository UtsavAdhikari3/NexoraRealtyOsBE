from datetime import date

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from agencies.localization import (
    convert_date,
    format_localized_date,
    format_nepal_address,
    format_nepal_currency,
    format_nepal_phone,
    render_message,
    to_latin_digits,
    to_nepali_digits,
)
from agencies.models import Agency
from agencies.serializers import AgencySerializer
from users.models import AgencyUser


class NepalLocalizationUtilityTests(TestCase):
    def test_known_nepali_new_year_conversion_round_trip(self):
        self.assertEqual(
            convert_date("2024-04-13", target="bs"),
            {"year": 2081, "month": 1, "day": 1},
        )
        self.assertEqual(
            convert_date("2081-01-01", target="ad"),
            {"year": 2024, "month": 4, "day": 13},
        )
        self.assertEqual(
            format_localized_date(
                date(2024, 4, 13),
                date_system="bs",
                language="ne",
                nepali_digits=True,
            ),
            "२०८१ वैशाख १ गते",
        )

    def test_nepali_digits_currency_and_phone_formatting(self):
        self.assertEqual(to_nepali_digits("2081"), "२०८१")
        self.assertEqual(to_latin_digits("२०८१"), "2081")
        self.assertEqual(
            format_nepal_currency(32_500_000, language="ne", nepali_digits=True),
            "रु. ३.२५ करोड",
        )
        self.assertEqual(
            format_nepal_phone("९८०१२३४५६७", nepali_digits=True),
            "+९७७ ९८० १२३ ४५६७",
        )

    def test_address_hierarchy_and_custom_template(self):
        agency = Agency.objects.create(
            name="नेपाल घरजग्गा",
            license_number="LOC-001",
            province="Bagmati",
            district="Kathmandu",
            municipality="Kathmandu Metropolitan City",
            ward_number="4",
            tole="Baluwatar",
            default_language="ne",
            message_templates={
                "lead_follow_up": {
                    "ne": {"body": "{lead_name} लाई {follow_up_date} मा फोन गर्नुहोस्।"}
                }
            },
        )
        self.assertEqual(
            format_nepal_address(agency, nepali_digits=True),
            "Baluwatar, Ward ४, Kathmandu Metropolitan City, Kathmandu, Bagmati, Nepal",
        )
        rendered = render_message(
            agency,
            "lead_follow_up",
            lead_name="राम",
            follow_up_date="२०८१ वैशाख १",
        )
        self.assertEqual(rendered["body"], "राम लाई २०८१ वैशाख १ मा फोन गर्नुहोस्।")


class AgencyLocalizationAPITests(APITestCase):
    def setUp(self):
        self.agency = Agency.objects.create(
            name="Nexora Nepal Realty",
            license_number="LOC-API-001",
            municipality="Lalitpur Metropolitan City",
            ward_number="3",
            tole="Jhamsikhel",
            district="Lalitpur",
            province="Bagmati",
            phone="9801234567",
            default_language="ne",
            default_date_system="bs",
            use_nepali_digits=True,
        )
        self.owner = AgencyUser.objects.create_user(
            email="localization@example.com",
            password="Password123",
            full_name="Localization Owner",
            agency=self.agency,
            role=AgencyUser.ROLE_AGENCY_OWNER,
        )
        self.client.force_authenticate(self.owner)

    def test_current_agency_exposes_localization_and_address_fields(self):
        response = self.client.get("/api/agencies/me/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["default_language"], "ne")
        self.assertEqual(response.data["default_date_system"], "bs")
        self.assertTrue(response.data["use_nepali_digits"])
        self.assertIn("वडा नं. ३", response.data["address_display"])
        self.assertEqual(response.data["phone_display"], "+९७७ ९८० १२३ ४५६७")
        self.assertIn("site_visit_confirmation", response.data["resolved_message_templates"])

    def test_localization_endpoint_converts_both_directions(self):
        response = self.client.post(
            "/api/agencies/localization/",
            {"date": "2024-04-13", "source": "ad", "target": "bs", "language": "ne", "use_nepali_digits": True},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["date"], "2081-01-01")
        self.assertEqual(response.data["display"], "२०८१ वैशाख १ गते")

        response = self.client.post(
            "/api/agencies/localization/",
            {"date": "२०८१-०१-०१", "source": "bs", "target": "ad", "use_nepali_digits": "false"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["date"], "2024-04-13")
        self.assertNotRegex(response.data["display"], "[०-९]")

    def test_serializer_rejects_non_nepal_timezone(self):
        serializer = AgencySerializer(
            self.agency,
            data={"timezone": "UTC"},
            partial=True,
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("timezone", serializer.errors)
