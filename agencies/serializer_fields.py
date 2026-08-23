from rest_framework import serializers

from .phone import (
    NEPAL_PHONE_ERROR,
    is_valid_nepal_phone,
    normalize_nepal_phone,
)


class NepalPhoneField(serializers.CharField):
    """DRF field that validates and stores Nepal phones consistently."""

    default_error_messages = {"invalid": NEPAL_PHONE_ERROR}

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        if value == "" and self.allow_blank:
            return value
        if not is_valid_nepal_phone(value):
            self.fail("invalid")
        return normalize_nepal_phone(value)
