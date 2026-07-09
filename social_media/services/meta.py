from urllib.parse import urlencode

import requests
from django.conf import settings


def graph_base_url():
    version = settings.META_GRAPH_VERSION
    return f"https://graph.facebook.com/{version}"


def build_meta_oauth_url(state):
    params = {
        "client_id": settings.META_APP_ID,
        "redirect_uri": settings.META_REDIRECT_URI,
        "state": state,
        "response_type": "code",
    }

    # Preferred: Facebook Login for Business configuration
    if getattr(settings, "META_LOGIN_CONFIG_ID", None):
        params["config_id"] = settings.META_LOGIN_CONFIG_ID
    else:
        # Safe fallback scopes that already worked for you
        params["scope"] = ",".join([
            "pages_show_list",
            "pages_read_engagement",
        ])

    return (
        f"https://www.facebook.com/{settings.META_GRAPH_VERSION}/dialog/oauth?"
        + urlencode(params)
    )


def exchange_code_for_short_token(code):
    url = f"{graph_base_url()}/oauth/access_token"

    response = requests.get(
        url,
        params={
            "client_id": settings.META_APP_ID,
            "client_secret": settings.META_APP_SECRET,
            "redirect_uri": settings.META_REDIRECT_URI,
            "code": code,
        },
        timeout=20,
    )

    response.raise_for_status()
    return response.json()


def exchange_short_token_for_long_token(short_lived_token):
    url = f"{graph_base_url()}/oauth/access_token"

    response = requests.get(
        url,
        params={
            "grant_type": "fb_exchange_token",
            "client_id": settings.META_APP_ID,
            "client_secret": settings.META_APP_SECRET,
            "fb_exchange_token": short_lived_token,
        },
        timeout=20,
    )

    response.raise_for_status()
    return response.json()


def get_facebook_pages(user_access_token):
    url = f"{graph_base_url()}/me/accounts"

    response = requests.get(
        url,
        params={
            "access_token": user_access_token,
            "fields": "id,name,access_token,instagram_business_account",
        },
        timeout=20,
    )

    response.raise_for_status()
    return response.json().get("data", [])


def get_instagram_account_from_page(page_id, page_access_token):
    url = f"{graph_base_url()}/{page_id}"

    response = requests.get(
        url,
        params={
            "access_token": page_access_token,
            "fields": "instagram_business_account{id,username,name}",
        },
        timeout=20,
    )

    response.raise_for_status()

    data = response.json()
    return data.get("instagram_business_account")


def publish_facebook_feed_post(page_id, page_access_token, message):
    url = f"{graph_base_url()}/{page_id}/feed"

    response = requests.post(
        url,
        data={
            "message": message,
            "access_token": page_access_token,
        },
        timeout=30,
    )

    response.raise_for_status()
    return response.json()