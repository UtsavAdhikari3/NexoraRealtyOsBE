from django.test import SimpleTestCase
from rest_framework import serializers

from .phone import is_valid_nepal_phone, normalize_nepal_phone
from .serializer_fields import NepalPhoneField


class PhoneSerializer(serializers.Serializer):
    phone = NepalPhoneField()


class NepalPhoneTests(SimpleTestCase):
    def test_normalizes_supported_mobile_prefixes(self):
        self.assertEqual(normalize_nepal_phone("9801234567"), "+9779801234567")
        self.assertEqual(normalize_nepal_phone("+977 9701234567"), "+9779701234567")
        self.assertTrue(is_valid_nepal_phone("९८०१२३४५६७"))

    def test_normalizes_requested_ten_digit_landline_format(self):
        self.assertEqual(normalize_nepal_phone("01-1234-5678"), "+9770112345678")

    def test_rejects_wrong_prefixes_and_lengths(self):
        for value in ["9601234567", "980123456", "98012345678", "+14155552671"]:
            with self.subTest(value=value):
                self.assertFalse(is_valid_nepal_phone(value))
                serializer = PhoneSerializer(data={"phone": value})
                self.assertFalse(serializer.is_valid())
                self.assertIn("10-digit Nepal phone number", str(serializer.errors["phone"][0]))

    def test_serializer_returns_prefixed_value(self):
        serializer = PhoneSerializer(data={"phone": "9801234567"})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["phone"], "+9779801234567")
