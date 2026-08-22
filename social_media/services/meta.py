import json
from urllib.parse import urlencode, urlsplit

import requests
from django.conf import settings


class MetaAPIError(Exception):
    def __init__(self, message, *, code=None, error_type=None, status_code=400):
        super().__init__(message)
        self.code = code
        self.error_type = error_type
        self.status_code = status_code


def raise_for_meta_error(response):
    if response.ok:
        return

    try:
        error = response.json().get("error", {})
    except ValueError:
        error = {}

    raise MetaAPIError(
        error.get("message", "Meta API request failed."),
        code=error.get("code"),
        error_type=error.get("type"),
        status_code=response.status_code,
    )


def graph_base_url():
    version = settings.META_GRAPH_VERSION
    return f"https://graph.facebook.com/{version}"


def meta_request_timeout():
    return (
        settings.META_HTTP_CONNECT_TIMEOUT_SECONDS,
        settings.META_HTTP_READ_TIMEOUT_SECONDS,
    )


def instagram_request_timeout():
    return (
        settings.META_HTTP_CONNECT_TIMEOUT_SECONDS,
        settings.META_INSTAGRAM_READ_TIMEOUT_SECONDS,
    )


def build_meta_oauth_url(state):
    params = {
        "client_id": settings.META_APP_ID,
        "redirect_uri": settings.META_REDIRECT_URI,
        "state": state,
        "response_type": "code",
        "auth_type": "rerequest",
    }

    # Preferred: Facebook Login for Business configuration
    if getattr(settings, "META_LOGIN_CONFIG_ID", None):
        params["config_id"] = settings.META_LOGIN_CONFIG_ID
    else:
        # Safe fallback scopes that already worked for you
        params["scope"] = ",".join([
            "pages_show_list",
            "pages_read_engagement",
            "pages_manage_posts",
            "instagram_basic",
            "instagram_content_publish",
            "instagram_manage_contents",
            "pages_messaging",
            "instagram_manage_messages",
        ])

    return (
        f"https://www.facebook.com/{settings.META_GRAPH_VERSION}/dialog/oauth?"
        + urlencode(params)
    )


def exchange_code_for_short_token(code):
    url = f"{graph_base_url()}/oauth/access_token"

    response = requests.post(
        url,
        data={
            "client_id": settings.META_APP_ID,
            "client_secret": settings.META_APP_SECRET,
            "redirect_uri": settings.META_REDIRECT_URI,
            "code": code,
        },
        timeout=meta_request_timeout(),
    )

    raise_for_meta_error(response)
    return response.json()


def exchange_short_token_for_long_token(short_lived_token):
    url = f"{graph_base_url()}/oauth/access_token"

    response = requests.post(
        url,
        data={
            "grant_type": "fb_exchange_token",
            "client_id": settings.META_APP_ID,
            "client_secret": settings.META_APP_SECRET,
            "fb_exchange_token": short_lived_token,
        },
        timeout=meta_request_timeout(),
    )

    raise_for_meta_error(response)
    return response.json()


def get_facebook_pages(user_access_token):
    url = f"{graph_base_url()}/me/accounts"
    params = {
        "fields": (
            "id,name,access_token,"
            "instagram_business_account{id,username,name}"
        ),
        "limit": 100,
    }
    pages = []

    # Meta paginates /me/accounts. Following the provider-issued `next` URL is
    # necessary for agencies that administer more than the first result page.
    for _ in range(10):
        response = requests.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {user_access_token}"},
            timeout=meta_request_timeout(),
        )
        raise_for_meta_error(response)
        payload = response.json()
        pages.extend(payload.get("data", []))
        url = (payload.get("paging") or {}).get("next")
        if not url:
            break
        params = None
    return pages


def get_instagram_account_from_page(page_id, page_access_token):
    url = f"{graph_base_url()}/{page_id}"

    response = requests.get(
        url,
        params={
            "fields": "instagram_business_account{id,username,name}",
        },
        headers={"Authorization": f"Bearer {page_access_token}"},
        timeout=meta_request_timeout(),
    )

    raise_for_meta_error(response)

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
        timeout=meta_request_timeout(),
    )

    raise_for_meta_error(response)
    return response.json()


def publish_facebook_photo_post(
    page_id,
    page_access_token,
    image_file,
    filename,
    content_type,
    message,
):
    response = requests.post(
        f"{graph_base_url()}/{page_id}/photos",
        data={
            "caption": message,
            "published": "true",
            "access_token": page_access_token,
        },
        files={
            "source": (filename, image_file, content_type),
        },
        timeout=meta_request_timeout(),
    )
    raise_for_meta_error(response)
    return response.json()


def upload_facebook_unpublished_photo(
    page_id,
    page_access_token,
    image_file,
    filename,
    content_type,
):
    response = requests.post(
        f"{graph_base_url()}/{page_id}/photos",
        data={
            "published": "false",
            "access_token": page_access_token,
        },
        files={
            "source": (filename, image_file, content_type),
        },
        timeout=meta_request_timeout(),
    )
    raise_for_meta_error(response)
    return response.json()


def publish_facebook_multi_photo_post(
    page_id,
    page_access_token,
    photo_ids,
    message,
):
    payload = {
        "message": message,
        "access_token": page_access_token,
    }
    for index, photo_id in enumerate(photo_ids):
        payload[f"attached_media[{index}]"] = json.dumps(
            {"media_fbid": photo_id}
        )

    response = requests.post(
        f"{graph_base_url()}/{page_id}/feed",
        data=payload,
        timeout=meta_request_timeout(),
    )
    raise_for_meta_error(response)
    return response.json()


def update_facebook_post(post_id, page_access_token, message):
    response = requests.post(
        f"{graph_base_url()}/{post_id}",
        data={
            "message": message,
            "access_token": page_access_token,
        },
        timeout=meta_request_timeout(),
    )
    raise_for_meta_error(response)
    data = response.json()
    if not data.get("success"):
        raise MetaAPIError("Meta did not confirm the Facebook post update.")
    return data


def delete_facebook_post(post_id, page_access_token):
    response = requests.delete(
        f"{graph_base_url()}/{post_id}",
        data={"access_token": page_access_token},
        timeout=meta_request_timeout(),
    )
    raise_for_meta_error(response)
    data = response.json()
    if not data.get("success"):
        raise MetaAPIError("Meta did not confirm the Facebook post deletion.")
    return data


def delete_instagram_media(media_id, user_access_token):
    version = settings.META_INSTAGRAM_MANAGEMENT_VERSION
    response = requests.delete(
        f"https://graph.facebook.com/{version}/{media_id}",
        data={"access_token": user_access_token},
        timeout=instagram_request_timeout(),
    )
    raise_for_meta_error(response)
    data = response.json()
    if not data.get("success"):
        raise MetaAPIError("Meta did not confirm the Instagram media deletion.")
    return data


def get_facebook_post_photo_id(post_id, page_access_token):
    response = requests.get(
        f"{graph_base_url()}/{post_id}",
        params={
            "fields": "attachments{target}",
            "access_token": page_access_token,
        },
        timeout=meta_request_timeout(),
    )
    raise_for_meta_error(response)
    attachments = response.json().get("attachments", {}).get("data", [])
    for attachment in attachments:
        media_id = attachment.get("target", {}).get("id")
        if media_id:
            return media_id
    raise MetaAPIError("Meta did not return the Facebook photo ID for this post.")


def create_instagram_image_container(
    instagram_account_id,
    page_access_token,
    image_url,
    caption="",
    is_carousel_item=False,
):
    payload = {
        "image_url": image_url,
        "access_token": page_access_token,
    }
    if caption:
        payload["caption"] = caption
    if is_carousel_item:
        payload["is_carousel_item"] = "true"

    response = requests.post(
        f"{graph_base_url()}/{instagram_account_id}/media",
        data=payload,
        timeout=instagram_request_timeout(),
    )
    raise_for_meta_error(response)
    return response.json()


def create_instagram_reel_container(
    instagram_account_id,
    page_access_token,
    video_url,
    caption="",
):
    payload = {
        "media_type": "REELS",
        "video_url": video_url,
        "share_to_feed": "true",
        "access_token": page_access_token,
    }
    if caption:
        payload["caption"] = caption
    response = requests.post(
        f"{graph_base_url()}/{instagram_account_id}/media",
        data=payload,
        timeout=instagram_request_timeout(),
    )
    raise_for_meta_error(response)
    return response.json()


def create_facebook_reel_session(page_id, page_access_token):
    response = requests.post(
        f"{graph_base_url()}/{page_id}/video_reels",
        data={
            "upload_phase": "start",
            "access_token": page_access_token,
        },
        timeout=instagram_request_timeout(),
    )
    raise_for_meta_error(response)
    return response.json()


def upload_facebook_hosted_reel(upload_url, page_access_token, video_url):
    hostname = (urlsplit(upload_url).hostname or "").lower()
    if not hostname.endswith(".facebook.com"):
        raise MetaAPIError("Meta returned an invalid Facebook Reel upload URL.")
    response = requests.post(
        upload_url,
        headers={
            "Authorization": f"OAuth {page_access_token}",
            "file_url": video_url,
        },
        timeout=instagram_request_timeout(),
    )
    raise_for_meta_error(response)
    data = response.json()
    if not data.get("success"):
        raise MetaAPIError("Meta did not confirm the Facebook Reel upload.")
    return data


def publish_facebook_reel_session(
    page_id,
    page_access_token,
    video_id,
    description="",
):
    response = requests.post(
        f"{graph_base_url()}/{page_id}/video_reels",
        data={
            "upload_phase": "finish",
            "video_state": "PUBLISHED",
            "video_id": video_id,
            "description": description,
            "access_token": page_access_token,
        },
        timeout=instagram_request_timeout(),
    )
    raise_for_meta_error(response)
    data = response.json()
    if not data.get("success"):
        raise MetaAPIError("Meta did not accept the Facebook Reel for publishing.")
    return data


def create_instagram_carousel_container(
    instagram_account_id,
    page_access_token,
    child_container_ids,
    caption,
):
    response = requests.post(
        f"{graph_base_url()}/{instagram_account_id}/media",
        data={
            "media_type": "CAROUSEL",
            "children": ",".join(child_container_ids),
            "caption": caption,
            "access_token": page_access_token,
        },
        timeout=instagram_request_timeout(),
    )
    raise_for_meta_error(response)
    return response.json()


def get_instagram_container_status(container_id, page_access_token):
    response = requests.get(
        f"{graph_base_url()}/{container_id}",
        params={"fields": "status_code,status"},
        headers={"Authorization": f"Bearer {page_access_token}"},
        timeout=instagram_request_timeout(),
    )
    raise_for_meta_error(response)
    return response.json()


def get_instagram_content_publishing_limit(
    instagram_account_id,
    page_access_token,
):
    response = requests.get(
        f"{graph_base_url()}/{instagram_account_id}/content_publishing_limit",
        params={
            "fields": "quota_usage,config",
            "access_token": page_access_token,
        },
        timeout=instagram_request_timeout(),
    )
    raise_for_meta_error(response)
    data = response.json().get("data", [])
    return data[0] if data else {}


def publish_instagram_container(
    instagram_account_id,
    page_access_token,
    container_id,
):
    response = requests.post(
        f"{graph_base_url()}/{instagram_account_id}/media_publish",
        data={
            "creation_id": container_id,
            "access_token": page_access_token,
        },
        timeout=instagram_request_timeout(),
    )
    raise_for_meta_error(response)
    return response.json()


def subscribe_page_to_webhooks(page_id, page_access_token):
    response = requests.post(
        f"{graph_base_url()}/{page_id}/subscribed_apps",
        data={
            "subscribed_fields": ",".join(
                [
                    "messages",
                    "messaging_postbacks",
                    "message_deliveries",
                    "message_reads",
                ]
            ),
            "access_token": page_access_token,
        },
        timeout=meta_request_timeout(),
    )
    raise_for_meta_error(response)
    return response.json()


def send_meta_text_message(account, recipient_external_id, text):
    payload = {
        "recipient": {"id": recipient_external_id},
        "message": {"text": text},
    }
    if account.platform == account.PLATFORM_FACEBOOK:
        payload["messaging_type"] = "RESPONSE"

    response = requests.post(
        f"{graph_base_url()}/{account.external_id}/messages",
        json=payload,
        headers={"Authorization": f"Bearer {account.access_token}"},
        timeout=meta_request_timeout(),
    )
    raise_for_meta_error(response)
    return response.json()


def get_meta_messaging_profile(account, external_user_id):
    """Resolve a PSID/IGSID using the Page token that received the message."""
    if account.platform == account.PLATFORM_INSTAGRAM:
        fields = ",".join(
            [
                "name",
                "username",
                "profile_pic",
                "follower_count",
                "is_user_follow_business",
                "is_business_follow_user",
                "is_verified_user",
            ]
        )
    else:
        fields = "first_name,last_name,profile_pic"

    response = requests.get(
        f"{graph_base_url()}/{external_user_id}",
        params={
            "fields": fields,
            "access_token": account.access_token,
        },
        timeout=(
            settings.META_HTTP_CONNECT_TIMEOUT_SECONDS,
            settings.META_PROFILE_READ_TIMEOUT_SECONDS,
        ),
    )
    raise_for_meta_error(response)
    return response.json()
