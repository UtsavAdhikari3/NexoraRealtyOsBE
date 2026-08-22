from django.utils.text import slugify


RESERVED_SUBDOMAINS = {
    "admin",
    "api",
    "app",
    "crm",
    "mail",
    "status",
    "support",
    "template",
    "www",
}


def normalize_subdomain(value):
    return slugify(str(value or "").strip())[:180]


def generated_agency_subdomain(agency_name):
    return normalize_subdomain(agency_name)


def subdomain_unavailable_message(subdomain):
    return f"{subdomain}.nexorarealtyos.com is unavailable. Choose a different agency name."
