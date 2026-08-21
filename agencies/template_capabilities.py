"""Capabilities implemented by each compiled public website template."""

from copy import deepcopy


TEMPLATE_CAPABILITIES = {
    "luxury-agency": {
        "template_key": "luxury-agency",
        "supported_schema_versions": [2],
        "supported_pages": [
            "home", "properties", "agents", "about", "contact", "valuation",
        ],
        "supported_sections": [
            "hero", "featured_properties", "property_categories", "services",
            "statistics", "about", "testimonials", "agents", "faqs",
            "newsletter", "contact_cta",
        ],
    },
}


def get_template_capabilities(template_key):
    """Return a copy so callers cannot mutate the process-wide registry."""
    capabilities = TEMPLATE_CAPABILITIES.get(template_key)
    return deepcopy(capabilities) if capabilities else None


def template_capability_errors(template_key, config):
    capabilities = get_template_capabilities(template_key)
    if not capabilities:
        return {"template": f"Unknown website template: {template_key}."}

    errors = {}
    if config.get("schema_version") not in capabilities["supported_schema_versions"]:
        errors["schema_version"] = "This template does not support the draft schema version."

    supported_pages = set(capabilities["supported_pages"])
    unsupported_pages = sorted(
        page for page, enabled in (config.get("enabled_pages") or {}).items()
        if enabled and page not in supported_pages
    )
    if unsupported_pages:
        errors["enabled_pages"] = f"This template does not render: {', '.join(unsupported_pages)}."

    for field in ("navigation", "footer_navigation"):
        unsupported = sorted({
            item.get("page") for item in (config.get(field) or [])
            if item.get("page") not in supported_pages
        })
        if unsupported:
            errors[field] = f"Remove unsupported pages: {', '.join(unsupported)}."

    supported_sections = set(capabilities["supported_sections"])
    unsupported_sections = sorted(
        section for section, visible in (config.get("section_visibility") or {}).items()
        if visible and section not in supported_sections
    )
    if unsupported_sections:
        errors["section_visibility"] = (
            f"This template does not render: {', '.join(unsupported_sections)}."
        )
    return errors


def normalize_config_for_template(template_key, config):
    """Disable/filter legacy controls that the selected template cannot render."""
    normalized = deepcopy(config or {})
    capabilities = get_template_capabilities(template_key)
    if not capabilities:
        return normalized
    pages = set(capabilities["supported_pages"])
    sections = set(capabilities["supported_sections"])
    normalized["enabled_pages"] = {
        key: bool(value) if key in pages else False
        for key, value in (normalized.get("enabled_pages") or {}).items()
    }
    for field in ("navigation", "footer_navigation"):
        normalized[field] = [
            item for item in (normalized.get(field) or []) if item.get("page") in pages
        ]
    normalized["section_visibility"] = {
        key: bool(value) if key in sections else False
        for key, value in (normalized.get("section_visibility") or {}).items()
    }
    normalized["section_order"] = [
        key for key in (normalized.get("section_order") or []) if key in sections
    ]
    return normalized
