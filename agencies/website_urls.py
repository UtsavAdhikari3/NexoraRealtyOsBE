from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from django.conf import settings
from django.utils.text import slugify


DEFAULT_STOREFRONT_URL = "http://localhost:5173/?tenant={slug}"


def agency_website_url(agency_or_slug):
    """Return the canonical public URL for an agency's published template."""
    domains = getattr(agency_or_slug, "website_domains", None)
    if domains is not None:
        primary = domains.filter(
            status="verified", is_active=True, is_primary=True
        ).only("domain").first()
        if primary:
            return f"https://{primary.domain}"
    slug = getattr(agency_or_slug, "slug", agency_or_slug)
    encoded_slug = quote(str(slug or "").strip(), safe="-")
    pattern = getattr(settings, "STOREFRONT_PUBLIC_URL", DEFAULT_STOREFRONT_URL).strip()

    if "{slug}" in pattern:
        return pattern.replace("{slug}", encoded_slug)

    # Backwards compatibility for an explicitly configured legacy storefront.
    return f"{pattern.rstrip('/')}/agency/{encoded_slug}"


def _append_path(url, path):
    parts = urlsplit(url)
    base_path = parts.path.rstrip("/")
    full_path = f"{base_path}/{path.lstrip('/')}" or "/"
    return urlunsplit((parts.scheme, parts.netloc, full_path, parts.query, parts.fragment))


def agency_page_url(agency, path=""):
    return _append_path(agency_website_url(agency), path) if path else agency_website_url(agency)


def property_website_url(property_obj):
    route_slug = property_obj.share_slug or f"{property_obj.id}-{slugify(property_obj.title) or 'property'}"
    return _append_path(
        agency_website_url(property_obj.agency),
        f"properties/{quote(route_slug, safe='-')}",
    )


def add_url_query(url, params):
    """Merge tracking parameters without discarding a tenant query parameter."""
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update({key: value for key, value in params.items() if value not in (None, "")})
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
