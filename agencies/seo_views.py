from xml.etree import ElementTree

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.utils.text import slugify
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from properties.public_selectors import public_properties

from .public_selectors import get_public_agency
from .template_capabilities import get_template_capabilities
from .website_urls import agency_page_url, property_website_url


User = get_user_model()
SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
PAGE_PATHS = {
    "home": "",
    "properties": "properties",
    "agents": "agents",
    "about": "about",
    "contact": "contact",
    "valuation": "list-your-property",
}


class PublicSitemapView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, license_number):
        agency = get_public_agency(license_number=license_number)
        config = agency.website_published_config or agency.website_config or {}
        capabilities = get_template_capabilities(agency.website_template) or {}
        supported = set(capabilities.get("supported_pages") or [])
        enabled = config.get("enabled_pages") or {}
        urls = []

        for page, path in PAGE_PATHS.items():
            if page in supported and enabled.get(page, page in {"home", "properties"}):
                urls.append((agency_page_url(agency, path), agency.website_published_at))

        for item in public_properties(agency=agency).only(
            "id", "title", "share_slug", "agency", "published_at", "updated_at"
        ).iterator():
            urls.append((property_website_url(item), item.updated_at or item.published_at))

        if "agents" in supported and enabled.get("agents", False):
            agents = User.objects.filter(agency=agency, role=User.ROLE_AGENT, is_active=True).only("id", "full_name")
            for agent in agents.iterator():
                slug = slugify(agent.full_name) or "agent"
                urls.append((agency_page_url(agency, f"agents/{agent.id}-{slug}"), None))

        root = ElementTree.Element("urlset", xmlns=SITEMAP_NS)
        for location, modified in urls:
            node = ElementTree.SubElement(root, "url")
            ElementTree.SubElement(node, "loc").text = location
            if modified:
                ElementTree.SubElement(node, "lastmod").text = modified.date().isoformat()
        return HttpResponse(
            ElementTree.tostring(root, encoding="utf-8", xml_declaration=True),
            content_type="application/xml",
        )


class PublicRobotsView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, license_number):
        agency = get_public_agency(license_number=license_number)
        content = "User-agent: *\nAllow: /\nSitemap: " + agency_page_url(agency, "sitemap.xml") + "\n"
        return HttpResponse(content, content_type="text/plain; charset=utf-8")
