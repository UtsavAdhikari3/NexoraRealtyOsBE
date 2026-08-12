import re
from copy import deepcopy

from rest_framework import serializers


HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
MAX_FAQS = 12
MAX_TESTIMONIALS = 8
MAX_STATISTICS = 6
MAX_SERVICES = 8

DEFAULT_WEBSITE_CONFIG = {
    "hero_eyebrow": "Trusted real estate guidance",
    "hero_title": "Find the right property with local experts",
    "hero_subtitle": "Explore verified properties and connect with our team for dependable guidance from inquiry to closing.",
    "mission": "",
    "story": "",
    "tagline": "",
    "secondary_color": "#8FAF9B",
    "accent_color": "#C8A96A",
    "services": [],
    "statistics": [],
    "testimonials": [],
    "faqs": [],
}


def default_website_config():
    return deepcopy(DEFAULT_WEBSITE_CONFIG)


def _clean_text(value, field, *, max_length, required=False):
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise serializers.ValidationError({field: "Must be text."})
    value = value.strip()
    if required and not value:
        raise serializers.ValidationError({field: "This field is required."})
    if len(value) > max_length:
        raise serializers.ValidationError({field: f"Must be {max_length} characters or fewer."})
    return value


def _clean_collection(value, field, *, maximum, fields):
    if value is None:
        return []
    if not isinstance(value, list):
        raise serializers.ValidationError({field: "Must be a list."})
    if len(value) > maximum:
        raise serializers.ValidationError({field: f"A maximum of {maximum} items is allowed."})

    cleaned = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise serializers.ValidationError({field: f"Item {index + 1} must be an object."})
        output = {}
        for key, settings in fields.items():
            raw = item.get(key, settings.get("default", ""))
            if settings.get("type") == "number":
                try:
                    number = int(raw)
                except (TypeError, ValueError):
                    raise serializers.ValidationError({field: f"Item {index + 1} {key} must be a number."})
                output[key] = max(settings.get("min", number), min(settings.get("max", number), number))
            else:
                output[key] = _clean_text(
                    raw,
                    f"{field}.{index}.{key}",
                    max_length=settings["max_length"],
                    required=settings.get("required", False),
                )
        cleaned.append(output)
    return cleaned


def validate_website_config(value):
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise serializers.ValidationError("Website configuration must be an object.")

    allowed = set(DEFAULT_WEBSITE_CONFIG)
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise serializers.ValidationError(f"Unknown website fields: {', '.join(unknown)}.")

    merged = {**default_website_config(), **value}
    cleaned = {
        "hero_eyebrow": _clean_text(merged["hero_eyebrow"], "hero_eyebrow", max_length=80),
        "hero_title": _clean_text(merged["hero_title"], "hero_title", max_length=120),
        "hero_subtitle": _clean_text(merged["hero_subtitle"], "hero_subtitle", max_length=320),
        "mission": _clean_text(merged["mission"], "mission", max_length=1500),
        "story": _clean_text(merged["story"], "story", max_length=3000),
        "tagline": _clean_text(merged["tagline"], "tagline", max_length=120),
    }

    for field in ["secondary_color", "accent_color"]:
        color = _clean_text(merged[field], field, max_length=7, required=True)
        if not HEX_COLOR_RE.fullmatch(color):
            raise serializers.ValidationError({field: "Enter a six-digit hex colour such as #496B5A."})
        cleaned[field] = color.upper()

    cleaned["services"] = _clean_collection(
        merged["services"], "services", maximum=MAX_SERVICES,
        fields={
            "title": {"max_length": 100, "required": True},
            "description": {"max_length": 320, "required": True},
        },
    )
    cleaned["statistics"] = _clean_collection(
        merged["statistics"], "statistics", maximum=MAX_STATISTICS,
        fields={
            "label": {"max_length": 80, "required": True},
            "value": {"max_length": 40, "required": True},
            "helper": {"max_length": 120},
        },
    )
    cleaned["testimonials"] = _clean_collection(
        merged["testimonials"], "testimonials", maximum=MAX_TESTIMONIALS,
        fields={
            "name": {"max_length": 100, "required": True},
            "role": {"max_length": 100},
            "location": {"max_length": 120},
            "quote": {"max_length": 600, "required": True},
            "rating": {"type": "number", "default": 5, "min": 1, "max": 5},
        },
    )
    cleaned["faqs"] = _clean_collection(
        merged["faqs"], "faqs", maximum=MAX_FAQS,
        fields={
            "question": {"max_length": 240, "required": True},
            "answer": {"max_length": 1200, "required": True},
        },
    )
    return cleaned


def website_readiness(agency):
    config = agency.website_draft_config or agency.website_config or default_website_config()
    checks = [
        ("agency_name", bool(agency.name.strip())),
        ("public_email", bool(agency.email)),
        ("phone", bool(agency.phone)),
        ("about", len((agency.about or "").strip()) >= 40),
        ("location", bool(agency.address or agency.municipality or agency.district)),
        ("logo", bool(agency.logo)),
        ("cover_image", bool(agency.cover_image)),
        ("hero_title", len((config.get("hero_title") or "").strip()) >= 8),
        ("hero_subtitle", len((config.get("hero_subtitle") or "").strip()) >= 20),
        ("seo_title", len((agency.seo_title or "").strip()) >= 8),
        ("seo_description", len((agency.seo_description or "").strip()) >= 40),
    ]
    missing = [name for name, ready in checks if not ready]
    completed = len(checks) - len(missing)
    return {
        "completion_percentage": round((completed / len(checks)) * 100),
        "is_ready_to_publish": not missing,
        "missing_fields": missing,
    }
