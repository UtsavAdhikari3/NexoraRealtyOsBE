from datetime import date
from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from .models import (
    Contact,
    CustomFieldDefinition,
    Deal,
    Lease,
    Owner,
)


def custom_field_in_use(definition):
    from leads.models import Lead
    from properties.models import Property

    models_by_module = {
        "lead": Lead,
        "contact": Contact,
        "property": Property,
        "deal": Deal,
        "owner": Owner,
        "lease": Lease,
    }
    model = models_by_module[definition.module]
    values = model.objects.filter(agency=definition.agency).exclude(
        custom_data={}
    ).values_list("custom_data", flat=True)
    return any(definition.key in (data or {}) for data in values.iterator())


def pipeline_stage_in_use(stage):
    if stage.module == "lead":
        from leads.models import Lead

        return Lead.objects.filter(agency=stage.agency, status=stage.key).exists()
    return Deal.objects.filter(agency=stage.agency, stage=stage.key).exists()


def validate_custom_data(agency, module, data):
    data = data or {}
    errors = {}
    definitions = CustomFieldDefinition.objects.filter(agency=agency, module=module, is_active=True)
    for field in definitions:
        value = data.get(field.key)
        if field.is_required and value in (None, "", []):
            errors[field.key] = f"{field.label} is required."
            continue
        if value in (None, "", []):
            continue
        if field.field_type == "number":
            try:
                Decimal(str(value))
            except (InvalidOperation, ValueError):
                errors[field.key] = f"{field.label} must be a number."
        elif field.field_type == "date":
            try:
                date.fromisoformat(str(value))
            except ValueError:
                errors[field.key] = f"{field.label} must be a date."
        elif field.field_type == "boolean" and not isinstance(value, bool):
            errors[field.key] = f"{field.label} must be true or false."
        elif field.field_type == "select" and field.options and value not in field.options:
            errors[field.key] = f"Choose a valid value for {field.label}."
        elif field.field_type == "multiselect" and (not isinstance(value, list) or any(item not in field.options for item in value)):
            errors[field.key] = f"Choose valid values for {field.label}."
    if errors:
        raise serializers.ValidationError({"custom_data": errors})
    return data
