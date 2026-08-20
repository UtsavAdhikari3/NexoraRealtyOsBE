import re
from copy import deepcopy
from urllib.parse import urlparse

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import URLValidator, validate_email
from django.utils import timezone
from rest_framework import serializers


HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
PHONE_RE = re.compile(r"^[+0-9()\-\s]{7,30}$")
MAX_FAQS = 12
MAX_TESTIMONIALS = 8
MAX_STATISTICS = 6
MAX_SERVICES = 12
MAX_PARTNERS = 12
MAX_NAV_ITEMS = 20
ALLOWED_FONTS = {"inter", "manrope", "poppins", "lato", "montserrat", "playfair-display", "noto-sans-devanagari"}
ALLOWED_PAGES = {
    "home", "properties", "map", "agents", "about", "mission", "story",
    "services", "faq", "contact", "schedule-viewing", "valuation",
}
LEGACY_REMOVED_PAGES = {"portal"}
DEFAULT_ENABLED_PAGES = {
    "home", "properties", "agents", "contact", "valuation",
}
ALLOWED_SECTIONS = {
    "hero", "featured_properties", "property_categories", "services", "statistics",
    "about", "mission", "vision", "testimonials", "agents", "faqs", "contact_cta",
    "social_links", "newsletter",
}
DEFAULT_SECTION_ORDER = [
    "hero", "statistics", "featured_properties", "property_categories", "services",
    "about", "agents", "testimonials", "faqs", "newsletter", "contact_cta",
]
DEFAULT_VISIBLE_SECTIONS = set(DEFAULT_SECTION_ORDER)
MEDIA_KEYS = {
    "logo", "logo_light", "logo_dark", "favicon", "hero_image",
    "property_placeholder", "social_share_image", "about_image", "partner_logos",
}


DEFAULT_WEBSITE_CONFIG = {
    "schema_version": 2,
    "primary_color": "#496B5A",
    "secondary_color": "#8FAF9B",
    "accent_color": "#C8A96A",
    "heading_font": "playfair-display",
    "body_font": "inter",
    "tagline": "",
    "about": "",
    "mission": "",
    "vision": "",
    "story": "",
    "year_established": "",
    "specialities": [],
    "areas_served": [],
    "hero_eyebrow": "",
    "hero_title": "",
    "hero_subtitle": "",
    "hero_primary_cta_label": "Explore properties",
    "hero_primary_cta_url": "/properties",
    "hero_secondary_cta_label": "Contact us",
    "hero_secondary_cta_url": "/contact",
    "newsletter_title": "",
    "newsletter_description": "",
    "contact_cta_eyebrow": "",
    "contact_cta_title": "",
    "contact_cta_subtitle": "",
    "contact_cta_label": "",
    "contact_cta_url": "/contact",
    "featured_property_limit": 6,
    "featured_property_mode": "latest",
    "featured_property_ids": [],
    "services": [],
    "statistics": [],
    "testimonials": [],
    "faqs": [],
    "enabled_pages": {page: page in DEFAULT_ENABLED_PAGES for page in ALLOWED_PAGES},
    "navigation": [],
    "footer_navigation": [],
    "section_visibility": {section: section in DEFAULT_VISIBLE_SECTIONS for section in ALLOWED_SECTIONS},
    "section_order": DEFAULT_SECTION_ORDER,
    "facebook_url": "",
    "instagram_url": "",
    "linkedin_url": "",
    "youtube_url": "",
    "tiktok_url": "",
    "whatsapp_number": "",
    "viber_number": "",
    "public_email": "",
    "public_phone": "",
    "address": "",
    "service_area": "",
    "business_hours": "",
    "map_latitude": None,
    "map_longitude": None,
    "seo_title": "",
    "seo_description": "",
    "og_title": "",
    "og_description": "",
    "language": "en",
    "legal_text": "",
    "copyright_text": "",
    "accuracy_confirmed": False,
    "media": {key: ([] if key == "partner_logos" else "") for key in MEDIA_KEYS},
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


def _clean_url(value, field, *, allow_internal=False):
    value = _clean_text(value, field, max_length=500)
    if not value:
        return ""
    if allow_internal and value.startswith("/") and not value.startswith("//"):
        return value
    try:
        URLValidator(schemes=["http", "https"])(value)
    except DjangoValidationError:
        raise serializers.ValidationError({field: "Enter a complete http:// or https:// URL."})
    if urlparse(value).scheme not in {"http", "https"}:
        raise serializers.ValidationError({field: "Only http and https URLs are supported."})
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
        unknown = set(item) - set(fields)
        if unknown:
            raise serializers.ValidationError({field: f"Item {index + 1} contains unsupported fields: {', '.join(sorted(unknown))}."})
        output = {}
        for key, settings in fields.items():
            raw = item.get(key, settings.get("default", ""))
            if settings.get("type") == "number":
                try:
                    number = int(raw)
                except (TypeError, ValueError):
                    raise serializers.ValidationError({field: f"Item {index + 1} {key} must be a number."})
                if number < settings.get("min", number) or number > settings.get("max", number):
                    raise serializers.ValidationError({field: f"Item {index + 1} {key} is outside the supported range."})
                output[key] = number
            elif settings.get("type") == "url":
                output[key] = _clean_url(raw, f"{field}.{index}.{key}", allow_internal=True)
            else:
                output[key] = _clean_text(raw, f"{field}.{index}.{key}", max_length=settings["max_length"], required=settings.get("required", False))
        cleaned.append(output)
    return cleaned


def _clean_string_list(value, field, maximum=20, max_length=120):
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > maximum:
        raise serializers.ValidationError({field: f"Must be a list with at most {maximum} items."})
    result = [_clean_text(item, field, max_length=max_length, required=True) for item in value]
    if len({item.casefold() for item in result}) != len(result):
        raise serializers.ValidationError({field: "Duplicate values are not allowed."})
    return result


def _clean_page_map(value, field):
    if not isinstance(value, dict):
        raise serializers.ValidationError({field: "Must be an object."})
    unknown = set(value) - ALLOWED_PAGES - LEGACY_REMOVED_PAGES
    if unknown:
        raise serializers.ValidationError({field: f"Unsupported pages: {', '.join(sorted(unknown))}."})
    result = {}
    for page in ALLOWED_PAGES:
        raw = value.get(page, DEFAULT_WEBSITE_CONFIG[field].get(page, False))
        if not isinstance(raw, bool):
            raise serializers.ValidationError({field: f"{page} must be true or false."})
        result[page] = raw
    return result


def _clean_section_map(value):
    if not isinstance(value, dict):
        raise serializers.ValidationError({"section_visibility": "Must be an object."})
    unknown = set(value) - ALLOWED_SECTIONS
    if unknown:
        raise serializers.ValidationError({"section_visibility": f"Unsupported sections: {', '.join(sorted(unknown))}."})
    result = {}
    for section in ALLOWED_SECTIONS:
        raw = value.get(section, True)
        if not isinstance(raw, bool):
            raise serializers.ValidationError({"section_visibility": f"{section} must be true or false."})
        result[section] = raw
    return result


def _clean_order(value, field, allowed, maximum):
    values = _clean_string_list(value, field, maximum=maximum, max_length=40)
    unknown = set(values) - allowed
    if unknown:
        raise serializers.ValidationError({field: f"Unsupported references: {', '.join(sorted(unknown))}."})
    return values


def _clean_navigation(value, field):
    if isinstance(value, list):
        value = [
            item for item in value
            if not isinstance(item, dict) or item.get("page") not in LEGACY_REMOVED_PAGES
        ]
    items = _clean_collection(value, field, maximum=MAX_NAV_ITEMS, fields={
        "page": {"max_length": 40, "required": True},
        "label": {"max_length": 40, "required": True},
        "url": {"max_length": 500},
    })
    pages = [item["page"] for item in items]
    if len(set(pages)) != len(pages):
        raise serializers.ValidationError({field: "A page may only appear once."})
    for item in items:
        if item["page"] not in ALLOWED_PAGES:
            raise serializers.ValidationError({field: f"Unsupported page: {item['page']}."})
        item["url"] = _clean_url(item["url"] or f"/{item['page']}", f"{field}.url", allow_internal=True)
    return items


def _clean_media(value):
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise serializers.ValidationError({"media": "Must be an object."})
    unknown = set(value) - MEDIA_KEYS
    if unknown:
        raise serializers.ValidationError({"media": f"Unsupported media fields: {', '.join(sorted(unknown))}."})
    result = {}
    for key in MEDIA_KEYS:
        raw = value.get(key, [] if key == "partner_logos" else "")
        if key == "partner_logos":
            result[key] = _clean_string_list(raw, "media.partner_logos", MAX_PARTNERS, 500)
        else:
            result[key] = _clean_text(raw, f"media.{key}", max_length=500)
    return result


def validate_website_config(value):
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise serializers.ValidationError("Website configuration must be an object.")
    unknown = sorted(set(value) - set(DEFAULT_WEBSITE_CONFIG))
    if unknown:
        raise serializers.ValidationError(f"Unknown website fields: {', '.join(unknown)}.")
    merged = {**default_website_config(), **value}
    if merged.get("schema_version") not in {2, None}:
        raise serializers.ValidationError({"schema_version": "Unsupported website configuration version."})
    cleaned = {"schema_version": 2}
    for field in ["primary_color", "secondary_color", "accent_color"]:
        color = _clean_text(merged[field], field, max_length=7, required=True)
        if not HEX_COLOR_RE.fullmatch(color):
            raise serializers.ValidationError({field: "Enter a six-digit hex colour such as #496B5A."})
        cleaned[field] = color.upper()
    for field in ["heading_font", "body_font"]:
        font = _clean_text(merged[field], field, max_length=50, required=True).lower()
        if font not in ALLOWED_FONTS:
            raise serializers.ValidationError({field: f"Choose one of: {', '.join(sorted(ALLOWED_FONTS))}."})
        cleaned[field] = font
    limits = {
        "tagline": 120, "about": 3000, "mission": 1500, "vision": 1500, "story": 5000,
        "year_established": 4, "hero_eyebrow": 80, "hero_title": 120, "hero_subtitle": 320,
        "hero_primary_cta_label": 40, "hero_secondary_cta_label": 40,
        "newsletter_title": 100, "newsletter_description": 320,
        "contact_cta_eyebrow": 80, "contact_cta_title": 140, "contact_cta_subtitle": 400, "contact_cta_label": 40,
        "public_email": 254, "public_phone": 30, "address": 500, "service_area": 300,
        "business_hours": 255, "whatsapp_number": 30, "viber_number": 30,
        "seo_title": 70, "seo_description": 180, "og_title": 70, "og_description": 200,
        "legal_text": 2000, "copyright_text": 300,
    }
    for field, maximum in limits.items():
        cleaned[field] = _clean_text(merged[field], field, max_length=maximum)
    if cleaned["public_email"]:
        try:
            validate_email(cleaned["public_email"])
        except DjangoValidationError:
            raise serializers.ValidationError({"public_email": "Enter a valid email address."})
    for field in ["public_phone", "whatsapp_number", "viber_number"]:
        if cleaned[field] and not PHONE_RE.fullmatch(cleaned[field]):
            raise serializers.ValidationError({field: "Enter a valid phone number."})
    for field in ["facebook_url", "instagram_url", "linkedin_url", "youtube_url", "tiktok_url"]:
        cleaned[field] = _clean_url(merged[field], field)
    for field in ["hero_primary_cta_url", "hero_secondary_cta_url", "contact_cta_url"]:
        cleaned[field] = _clean_url(merged[field], field, allow_internal=True)
    cleaned["specialities"] = _clean_string_list(merged["specialities"], "specialities")
    cleaned["areas_served"] = _clean_string_list(merged["areas_served"], "areas_served")
    cleaned["services"] = _clean_collection(merged["services"], "services", maximum=MAX_SERVICES, fields={"title": {"max_length": 100, "required": True}, "description": {"max_length": 500, "required": True}})
    cleaned["statistics"] = _clean_collection(merged["statistics"], "statistics", maximum=MAX_STATISTICS, fields={"label": {"max_length": 80, "required": True}, "value": {"max_length": 40, "required": True}, "helper": {"max_length": 120}})
    cleaned["testimonials"] = _clean_collection(merged["testimonials"], "testimonials", maximum=MAX_TESTIMONIALS, fields={"name": {"max_length": 100, "required": True}, "role": {"max_length": 100}, "location": {"max_length": 120}, "quote": {"max_length": 600, "required": True}, "rating": {"type": "number", "default": 5, "min": 1, "max": 5}})
    cleaned["faqs"] = _clean_collection(merged["faqs"], "faqs", maximum=MAX_FAQS, fields={"question": {"max_length": 240, "required": True}, "answer": {"max_length": 1200, "required": True}})
    cleaned["enabled_pages"] = _clean_page_map(merged["enabled_pages"], "enabled_pages")
    cleaned["navigation"] = _clean_navigation(merged["navigation"], "navigation")
    cleaned["footer_navigation"] = _clean_navigation(merged["footer_navigation"], "footer_navigation")
    for field in ["navigation", "footer_navigation"]:
        disabled = [
            item["page"] for item in cleaned[field]
            if not cleaned["enabled_pages"].get(item["page"], False)
        ]
        if disabled:
            raise serializers.ValidationError({
                field: f"Enable these pages before adding them to navigation: {', '.join(disabled)}."
            })
    cleaned["section_visibility"] = _clean_section_map(merged["section_visibility"])
    cleaned["section_order"] = _clean_order(merged["section_order"], "section_order", ALLOWED_SECTIONS, len(ALLOWED_SECTIONS))
    try:
        cleaned["featured_property_limit"] = int(merged["featured_property_limit"])
    except (TypeError, ValueError):
        raise serializers.ValidationError({"featured_property_limit": "Must be a number."})
    if cleaned["featured_property_limit"] < 1 or cleaned["featured_property_limit"] > 24:
        raise serializers.ValidationError({"featured_property_limit": "Choose between 1 and 24."})
    cleaned["featured_property_mode"] = _clean_text(merged["featured_property_mode"], "featured_property_mode", max_length=20, required=True)
    if cleaned["featured_property_mode"] not in {"latest", "manual", "featured"}:
        raise serializers.ValidationError({"featured_property_mode": "Choose latest, manual, or featured."})
    if not isinstance(merged["featured_property_ids"], list):
        raise serializers.ValidationError({"featured_property_ids": "Choose properties from a list."})
    try:
        cleaned["featured_property_ids"] = list(dict.fromkeys(int(item) for item in merged["featured_property_ids"]))
    except (TypeError, ValueError):
        raise serializers.ValidationError({"featured_property_ids": "Property IDs must be whole numbers."})
    if any(item < 1 for item in cleaned["featured_property_ids"]):
        raise serializers.ValidationError({"featured_property_ids": "Property IDs must be positive."})
    if len(cleaned["featured_property_ids"]) > 24:
        raise serializers.ValidationError({"featured_property_ids": "Choose no more than 24 properties."})
    if cleaned["featured_property_mode"] == "manual" and len(cleaned["featured_property_ids"]) > cleaned["featured_property_limit"]:
        raise serializers.ValidationError({"featured_property_ids": "The selection cannot exceed the featured-property limit."})
    cleaned["language"] = _clean_text(merged["language"], "language", max_length=2, required=True)
    if cleaned["language"] not in {"en", "ne"}:
        raise serializers.ValidationError({"language": "Choose English or Nepali."})
    for field, low, high in [("map_latitude", -90, 90), ("map_longitude", -180, 180)]:
        raw = merged[field]
        if raw in (None, ""):
            cleaned[field] = None
        else:
            try:
                cleaned[field] = float(raw)
            except (TypeError, ValueError):
                raise serializers.ValidationError({field: "Must be a number."})
            if not low <= cleaned[field] <= high:
                raise serializers.ValidationError({field: "Coordinate is outside the valid range."})
    if not isinstance(merged["accuracy_confirmed"], bool):
        raise serializers.ValidationError({"accuracy_confirmed": "Must be true or false."})
    cleaned["accuracy_confirmed"] = merged["accuracy_confirmed"]
    cleaned["media"] = _clean_media(merged["media"])
    return cleaned


def materialize_website_config(agency, value=None):
    """Normalize legacy JSON and snapshot every public agency field into one draft."""
    raw = deepcopy(value or agency.website_draft_config or agency.website_published_config or agency.website_config or {})
    media = dict(raw.get("media") or {})
    if agency.logo and not media.get("logo"):
        media["logo"] = agency.logo.name
    if agency.cover_image and not media.get("hero_image"):
        media["hero_image"] = agency.cover_image.name
    raw["media"] = media
    mappings = {
        "primary_color": agency.primary_color or "#496B5A", "about": agency.about,
        "public_email": agency.email or "", "public_phone": agency.phone or "",
        "address": agency.address, "business_hours": agency.business_hours,
        "facebook_url": agency.facebook_url or "", "instagram_url": agency.instagram_url or "",
        "linkedin_url": agency.linkedin_url or "", "youtube_url": agency.youtube_url or "",
        "tiktok_url": agency.tiktok_url or "", "whatsapp_number": agency.whatsapp_number or "",
        "viber_number": agency.viber_number or "", "seo_title": agency.seo_title,
        "seo_description": agency.seo_description, "language": agency.default_language,
    }
    for key, fallback in mappings.items():
        if not raw.get(key) and fallback:
            raw[key] = fallback
    return validate_website_config(raw)


def website_readiness(agency, config=None):
    from .template_capabilities import template_capability_errors

    config = materialize_website_config(agency, config)
    media = config.get("media", {})
    checks = [
        ("agency_name", bool((agency.name or "").strip())),
        ("public_contact", bool(config["public_email"] or config["public_phone"])),
        ("about", len(config["about"]) >= 40),
        ("location", bool(config["address"] or config["service_area"])),
        ("logo", bool(media.get("logo"))),
        ("primary_color", bool(config["primary_color"])),
        ("hero_title", len(config["hero_title"]) >= 8),
        ("seo_title", len(config["seo_title"]) >= 8),
        ("seo_description", len(config["seo_description"]) >= 40),
        ("accuracy_confirmed", config["accuracy_confirmed"] is True),
    ]
    page_checks = {
        "about_page_content": (
            not config["enabled_pages"].get("about") or len(config["about"]) >= 40
        ),
        "mission_page_content": (
            not config["enabled_pages"].get("mission") or len(config["mission"]) >= 20
        ),
        "story_page_content": (
            not config["enabled_pages"].get("story") or len(config["story"]) >= 40
        ),
        "services_page_content": (
            not config["enabled_pages"].get("services") or bool(config["services"])
        ),
        "faq_page_content": (
            not config["enabled_pages"].get("faq") or bool(config["faqs"])
        ),
        "map_page_location": (
            not config["enabled_pages"].get("map")
            or bool(config["address"] or config["service_area"])
        ),
    }
    checks.extend(page_checks.items())
    capability_errors = template_capability_errors(agency.website_template, config)
    missing = [name for name, ready in checks if not ready]
    if capability_errors:
        missing.append("template_capabilities")
    completed = len(checks) - len(missing)
    return {
        "completion_percentage": round((completed / len(checks)) * 100),
        "is_ready_to_publish": not missing,
        "missing_fields": missing,
        "checks": {name: ready for name, ready in checks},
        "capability_errors": capability_errors,
    }


def merge_website_changes(current, changes):
    """Recursively merge maps while replacing arrays and scalars atomically."""
    if not isinstance(current, dict) or not isinstance(changes, dict):
        return deepcopy(changes)
    merged = deepcopy(current)
    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_website_changes(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def advance_website_draft_revision(agency, user=None):
    agency.website_draft_revision += 1
    agency.website_draft_updated_at = timezone.now()
    agency.website_draft_updated_by = user if getattr(user, "is_authenticated", False) else None
    return ["website_draft_revision", "website_draft_updated_at", "website_draft_updated_by"]
