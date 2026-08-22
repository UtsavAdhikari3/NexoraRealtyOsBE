import time
import mimetypes
from pathlib import PurePosixPath
from urllib.parse import urljoin, urlsplit

import requests
from django.conf import settings
from django.utils import timezone
from PIL import Image, UnidentifiedImageError

from social_media.models import SocialAccount, SocialPost, SocialPublishResult
from .meta import (
    MetaAPIError,
    create_facebook_reel_session,
    create_instagram_carousel_container,
    create_instagram_image_container,
    create_instagram_reel_container,
    get_instagram_content_publishing_limit,
    get_instagram_container_status,
    publish_facebook_feed_post,
    publish_facebook_multi_photo_post,
    publish_facebook_photo_post,
    publish_facebook_reel_session,
    publish_instagram_container,
    upload_facebook_hosted_reel,
    upload_facebook_unpublished_photo,
)


def get_post_images(post):
    media_images = [item.image for item in post.media_items.all()]
    if media_images:
        return media_images
    return [post.image] if post.image else []


def get_public_media_url(post, image_file=None):
    image_file = image_file or post.image
    if not image_file:
        raise ValueError("Image publishing requires an uploaded image.")

    base_url = getattr(settings, "PUBLIC_API_BASE_URL", "").strip()
    if not base_url:
        redirect = urlsplit(settings.META_REDIRECT_URI)
        base_url = f"{redirect.scheme}://{redirect.netloc}"

    parsed_base_url = urlsplit(base_url)
    if (
        not base_url
        or parsed_base_url.scheme != "https"
        or parsed_base_url.hostname in {"localhost", "127.0.0.1"}
    ):
        raise ValueError(
            "Configure PUBLIC_API_BASE_URL with a public HTTPS URL so Meta can fetch the media."
        )

    return urljoin(f"{base_url.rstrip('/')}/", image_file.url.lstrip("/"))


def get_public_image_url(post, image_file=None):
    image_file = image_file or post.image
    image_url = get_public_media_url(post, image_file=image_file)
    extension = PurePosixPath(image_file.name).suffix.lower()
    if extension not in {".jpg", ".jpeg"}:
        raise ValueError("Instagram image publishing currently requires a JPEG image.")

    try:
        with image_file.open("rb") as opened_image:
            image = Image.open(opened_image)
            image.verify()
        with image_file.open("rb") as opened_image:
            image = Image.open(opened_image)
            width, height = image.size
            image_format = image.format
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("The uploaded Instagram image is not a valid JPEG.") from exc

    if image_format != "JPEG":
        raise ValueError("Instagram image publishing currently requires a JPEG image.")
    if image_file.size > 8 * 1024 * 1024:
        raise ValueError("Instagram images cannot exceed 8 MB.")
    if width < 320:
        raise ValueError("Instagram images must be at least 320 pixels wide.")

    aspect_ratio = width / height
    if not 0.8 <= aspect_ratio <= 1.91:
        raise ValueError(
            "Instagram image aspect ratio must be between 4:5 and 1.91:1. "
            f"Uploaded image is {width}x{height} ({aspect_ratio:.2f}:1)."
        )
    return image_url


def get_public_video_url(post):
    if not post.video:
        raise ValueError("Reel publishing requires an uploaded video.")
    video_url = get_public_media_url(post, image_file=post.video)
    if PurePosixPath(post.video.name).suffix.lower() != ".mp4":
        raise ValueError("The stored Reel must be an MP4 video.")
    if post.video.size > settings.SOCIAL_REEL_MAX_SIZE_BYTES:
        raise ValueError(
            f"The stored Reel exceeds the {settings.SOCIAL_REEL_MAX_SIZE_MB} MB limit."
        )
    return video_url


def find_target_account(post, platform):
    selected = post.social_account
    if selected and selected.platform == platform:
        return selected

    queryset = SocialAccount.objects.filter(
        agency=post.agency,
        provider=SocialAccount.PROVIDER_META,
        platform=platform,
        status=SocialAccount.STATUS_CONNECTED,
    )

    if selected and selected.page_id:
        queryset = queryset.filter(page_id=selected.page_id)

    return queryset.order_by("id").first()


def enforce_instagram_publish_quota(account):
    """Fail before container creation when the rolling publish quota is full."""
    window_start = timezone.now() - timezone.timedelta(hours=24)
    configured_limit = settings.INSTAGRAM_PUBLISH_QUOTA_LIMIT
    local_usage = SocialPublishResult.objects.filter(
        social_account=account,
        platform=SocialAccount.PLATFORM_INSTAGRAM,
        status=SocialPublishResult.STATUS_PUBLISHED,
        published_at__gte=window_start,
    ).count()
    if local_usage >= configured_limit:
        raise ValueError(
            "Instagram's 24-hour publishing quota has been reached for this "
            f"account ({local_usage}/{configured_limit}). Try again later."
        )

    if not settings.META_REMOTE_QUOTA_CHECK_ENABLED:
        return

    quota = get_instagram_content_publishing_limit(
        instagram_account_id=account.external_id,
        page_access_token=account.access_token,
    )
    provider_usage = quota.get("quota_usage")
    config = quota.get("config") or {}
    if isinstance(config, list):
        config = config[0] if config else {}
    provider_limit = config.get("quota_total") or configured_limit
    if provider_usage is not None and int(provider_usage) >= int(provider_limit):
        raise ValueError(
            "Instagram's provider-reported 24-hour publishing quota has been "
            f"reached ({provider_usage}/{provider_limit}). Try again later."
        )


def wait_for_instagram_container(container_id, page_access_token):
    attempts = settings.INSTAGRAM_CONTAINER_POLL_ATTEMPTS
    interval = settings.INSTAGRAM_CONTAINER_POLL_INTERVAL_SECONDS
    deadline = time.monotonic() + settings.INSTAGRAM_PUBLISH_DEADLINE_SECONDS
    last_status = None

    for attempt in range(attempts):
        if time.monotonic() >= deadline:
            break
        status_data = get_instagram_container_status(
            container_id=container_id,
            page_access_token=page_access_token,
        )
        last_status = status_data.get("status_code")
        if last_status == "FINISHED":
            break
        if last_status in {"ERROR", "EXPIRED"}:
            raise ValueError(
                status_data.get("status")
                or f"Instagram media container entered {last_status} status."
            )
        if attempt < attempts - 1 and interval:
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(interval, remaining))
    if last_status != "FINISHED":
        raise ValueError(
            "Instagram media processing did not finish before the publishing "
            f"deadline (last status: {last_status or 'unknown'}). Verify that "
            "the uploaded media URL is publicly reachable over HTTPS."
        )


def publish_instagram_images(post, account, result=None):
    images = get_post_images(post)
    if not images:
        raise ValueError("Instagram publishing requires at least one image.")

    if len(images) == 1:
        image_url = get_public_image_url(post, image_file=images[0])
        container_data = create_instagram_image_container(
            instagram_account_id=account.external_id,
            page_access_token=account.access_token,
            image_url=image_url,
            caption=post.caption,
        )
        container_id = container_data.get("id")
        if not container_id:
            raise ValueError("Meta did not return an Instagram media container ID.")
    else:
        child_container_ids = []
        for image_file in images:
            image_url = get_public_image_url(post, image_file=image_file)
            child_data = create_instagram_image_container(
                instagram_account_id=account.external_id,
                page_access_token=account.access_token,
                image_url=image_url,
                is_carousel_item=True,
            )
            child_container_id = child_data.get("id")
            if not child_container_id:
                raise ValueError(
                    "Meta did not return an Instagram carousel item container ID."
                )
            wait_for_instagram_container(
                child_container_id,
                account.access_token,
            )
            child_container_ids.append(child_container_id)

        carousel_data = create_instagram_carousel_container(
            instagram_account_id=account.external_id,
            page_access_token=account.access_token,
            child_container_ids=child_container_ids,
            caption=post.caption,
        )
        container_id = carousel_data.get("id")
        if not container_id:
            raise ValueError("Meta did not return an Instagram carousel container ID.")

    if result is not None:
        result.container_id = container_id
        result.save(update_fields=["container_id", "updated_at"])

    wait_for_instagram_container(container_id, account.access_token)

    publish_data = publish_instagram_container(
        instagram_account_id=account.external_id,
        page_access_token=account.access_token,
        container_id=container_id,
    )
    external_post_id = publish_data.get("id")
    if not external_post_id:
        raise ValueError("Meta did not return an Instagram media ID.")
    return container_id, external_post_id


def publish_instagram_image(post, account, result=None):
    """Backwards-compatible name for the one-or-many image publisher."""
    return publish_instagram_images(post, account, result=result)


def publish_instagram_reel(post, account, result=None):
    video_url = get_public_video_url(post)
    container_data = create_instagram_reel_container(
        instagram_account_id=account.external_id,
        page_access_token=account.access_token,
        video_url=video_url,
        caption=post.caption,
    )
    container_id = container_data.get("id")
    if not container_id:
        raise ValueError("Meta did not return an Instagram Reel container ID.")
    if result is not None:
        result.container_id = container_id
        result.save(update_fields=["container_id", "updated_at"])
    wait_for_instagram_container(container_id, account.access_token)
    publish_data = publish_instagram_container(
        instagram_account_id=account.external_id,
        page_access_token=account.access_token,
        container_id=container_id,
    )
    external_post_id = publish_data.get("id")
    if not external_post_id:
        raise ValueError("Meta did not return an Instagram Reel ID.")
    return container_id, external_post_id


def publish_facebook_reel(post, account):
    video_url = get_public_video_url(post)
    page_id = account.page_id or account.external_id
    session = create_facebook_reel_session(page_id, account.access_token)
    video_id = session.get("video_id")
    upload_url = session.get("upload_url")
    if not video_id or not upload_url:
        raise ValueError("Meta did not return a Facebook Reel upload session.")
    upload_facebook_hosted_reel(
        upload_url=upload_url,
        page_access_token=account.access_token,
        video_url=video_url,
    )
    publish_facebook_reel_session(
        page_id=page_id,
        page_access_token=account.access_token,
        video_id=video_id,
        description=post.caption,
    )
    return video_id


def publish_facebook_images(post, account, images):
    page_id = account.page_id or account.external_id
    if len(images) == 1:
        image_file = images[0]
        with image_file.open("rb") as opened_image:
            data = publish_facebook_photo_post(
                page_id=page_id,
                page_access_token=account.access_token,
                image_file=opened_image,
                filename=PurePosixPath(image_file.name).name,
                content_type=(
                    mimetypes.guess_type(image_file.name)[0]
                    or "application/octet-stream"
                ),
                message=post.caption,
            )
        return data, data.get("id", "")

    photo_ids = []
    for image_file in images:
        with image_file.open("rb") as opened_image:
            upload_data = upload_facebook_unpublished_photo(
                page_id=page_id,
                page_access_token=account.access_token,
                image_file=opened_image,
                filename=PurePosixPath(image_file.name).name,
                content_type=(
                    mimetypes.guess_type(image_file.name)[0]
                    or "application/octet-stream"
                ),
            )
        photo_id = upload_data.get("id")
        if not photo_id:
            raise ValueError("Meta did not return a Facebook photo ID.")
        photo_ids.append(photo_id)

    data = publish_facebook_multi_photo_post(
        page_id=page_id,
        page_access_token=account.access_token,
        photo_ids=photo_ids,
        message=post.caption,
    )
    return data, photo_ids[0]


def publish_target(post, account):
    result, _ = SocialPublishResult.objects.get_or_create(
        post=post,
        social_account=account,
        defaults={"platform": account.platform},
    )

    if result.status == SocialPublishResult.STATUS_PUBLISHED:
        return result

    result.platform = account.platform
    result.status = SocialPublishResult.STATUS_PENDING
    result.error_message = ""
    result.attempt_count += 1
    result.save(
        update_fields=[
            "platform",
            "status",
            "error_message",
            "attempt_count",
            "updated_at",
        ]
    )

    try:
        if account.platform == SocialAccount.PLATFORM_FACEBOOK:
            if post.post_format == SocialPost.FORMAT_REEL:
                video_id = publish_facebook_reel(post, account)
                result.external_media_id = video_id
                result.external_post_id = video_id
            else:
                images = get_post_images(post)
                if images:
                    data, first_media_id = publish_facebook_images(post, account, images)
                    result.external_media_id = first_media_id
                    result.external_post_id = data.get("post_id") or data.get("id", "")
                else:
                    data = publish_facebook_feed_post(
                        page_id=account.page_id or account.external_id,
                        page_access_token=account.access_token,
                        message=post.caption,
                    )
                    result.external_post_id = data.get("id", "")
                    result.external_media_id = ""
            result.container_id = ""
        elif account.platform == SocialAccount.PLATFORM_INSTAGRAM:
            enforce_instagram_publish_quota(account)
            if post.post_format == SocialPost.FORMAT_REEL:
                result.container_id, result.external_post_id = publish_instagram_reel(
                    post,
                    account,
                    result=result,
                )
            else:
                result.container_id, result.external_post_id = publish_instagram_images(
                    post,
                    account,
                    result=result,
                )
            result.external_media_id = result.external_post_id
        else:
            raise ValueError(f"Publishing to {account.platform} is not supported.")

        if not result.external_post_id:
            raise ValueError("Meta did not return a published post ID.")

        result.status = SocialPublishResult.STATUS_PUBLISHED
        result.published_at = timezone.now()
        result.error_message = ""
        result.save()
        return result
    except requests.Timeout:
        result.status = SocialPublishResult.STATUS_FAILED
        if account.platform == SocialAccount.PLATFORM_INSTAGRAM:
            result.error_message = (
                "Meta timed out while publishing to Instagram. Verify that the uploaded "
                "media URL is publicly reachable over HTTPS, then retry."
            )
        else:
            result.error_message = (
                f"Meta timed out while publishing to {account.platform}. Please retry."
            )
        result.save(update_fields=["status", "error_message", "updated_at"])
        return result
    except MetaAPIError as exc:
        result.status = SocialPublishResult.STATUS_FAILED
        if exc.code in {4, 17, 32, 613}:
            result.error_message = (
                "Meta temporarily rate-limited this account. Wait before retrying. "
                f"Provider message: {exc}"
            )
        elif exc.code == 190:
            result.error_message = (
                "The Meta connection expired or was revoked. Reconnect the account "
                "before retrying."
            )
            account.status = SocialAccount.STATUS_EXPIRED
            account.save(update_fields=["status", "updated_at"])
        else:
            result.error_message = str(exc)
        result.save(update_fields=["status", "error_message", "updated_at"])
        return result
    except Exception as exc:
        result.status = SocialPublishResult.STATUS_FAILED
        result.error_message = str(exc)
        result.save(update_fields=["status", "error_message", "updated_at"])
        return result


def publish_social_post(post, platforms=None):
    platforms = platforms or post.target_platforms or [post.platform]
    platforms = list(dict.fromkeys(platforms))
    results = []
    missing_errors = []

    for platform in platforms:
        account = find_target_account(post, platform)
        if account is None:
            missing_errors.append(f"No connected {platform} account was found.")
            continue
        results.append(publish_target(post, account))

    published_results = [
        result
        for result in results
        if result.status == SocialPublishResult.STATUS_PUBLISHED
    ]
    failed_results = [
        result
        for result in results
        if result.status == SocialPublishResult.STATUS_FAILED
    ]
    errors = missing_errors + [result.error_message for result in failed_results]

    if published_results and not errors:
        post.status = SocialPost.STATUS_PUBLISHED
        post.published_at = max(result.published_at for result in published_results)
    elif published_results:
        post.status = SocialPost.STATUS_PARTIAL
        post.published_at = max(result.published_at for result in published_results)
    else:
        post.status = SocialPost.STATUS_FAILED
        post.published_at = None

    facebook_result = next(
        (
            result
            for result in published_results
            if result.platform == SocialAccount.PLATFORM_FACEBOOK
        ),
        None,
    )
    primary_result = facebook_result or (published_results[0] if published_results else None)
    post.external_post_id = primary_result.external_post_id if primary_result else ""
    post.error_message = " | ".join(error for error in errors if error)
    post.target_platforms = platforms
    post.save(
        update_fields=[
            "status",
            "published_at",
            "external_post_id",
            "error_message",
            "target_platforms",
            "updated_at",
        ]
    )
    return post
