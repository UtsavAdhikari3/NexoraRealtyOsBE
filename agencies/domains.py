import ipaddress
import re
from urllib.parse import urlsplit

import requests
from django.conf import settings
from rest_framework import serializers


DOMAIN_RE = re.compile(r"^(?=.{1,253}\.?$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}\.?$")


def normalize_domain(value):
    raw = str(value or "").strip()
    if not raw:
        raise serializers.ValidationError("Enter a domain name.")
    parsed = urlsplit(raw if "://" in raw else f"//{raw}")
    if parsed.username or parsed.password or parsed.port:
        raise serializers.ValidationError("Enter a hostname without credentials or a port.")
    hostname = (parsed.hostname or "").rstrip(".")
    try:
        hostname = hostname.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise serializers.ValidationError("Enter a valid domain name.") from exc
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise serializers.ValidationError("IP addresses cannot be claimed as custom domains.")
    if hostname == "localhost" or not DOMAIN_RE.fullmatch(hostname):
        raise serializers.ValidationError("Enter a valid public domain name.")
    platform_suffix = getattr(settings, "PLATFORM_DOMAIN_SUFFIX", "nexorarealtyos.com").lower().strip(".")
    if hostname == platform_suffix or hostname.endswith(f".{platform_suffix}"):
        raise serializers.ValidationError("Platform-managed domains cannot be claimed.")
    return hostname


def verification_record(domain):
    return {
        "type": "TXT",
        "host": f"_nexora-verification.{domain.domain}",
        "value": f"nexora-verification={domain.verification_token}",
    }


def routing_record(domain):
    return {
        "type": "CNAME",
        "host": domain.domain,
        "value": getattr(settings, "CUSTOM_DOMAIN_CNAME_TARGET", "sites.nexorarealtyos.com"),
    }


def dns_txt_values(hostname):
    endpoint = getattr(settings, "DNS_OVER_HTTPS_URL", "https://cloudflare-dns.com/dns-query")
    response = requests.get(
        endpoint,
        params={"name": hostname, "type": "TXT"},
        headers={"Accept": "application/dns-json"},
        timeout=5,
    )
    response.raise_for_status()
    answers = response.json().get("Answer") or []
    values = []
    for answer in answers:
        if answer.get("type") != 16:
            continue
        # DNS JSON represents TXT chunks as adjacent quoted strings.
        values.append("".join(re.findall(r'"([^"]*)"', answer.get("data", ""))))
    return values


def verify_domain_ownership(domain):
    expected = verification_record(domain)["value"]
    try:
        return expected in dns_txt_values(verification_record(domain)["host"])
    except (requests.RequestException, ValueError):
        return False
