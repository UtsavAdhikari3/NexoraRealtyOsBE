from django.utils import timezone

from social_media.models import SocialAccount, SocialPost
from .meta import publish_facebook_feed_post


def publish_social_post(post):
    account = post.social_account
    if not account:
        raise ValueError("Select a connected social account first.")
    if account.status != SocialAccount.STATUS_CONNECTED:
        raise ValueError("The selected social account is disconnected.")
    if account.platform != SocialAccount.PLATFORM_FACEBOOK:
        raise ValueError("MVP direct publishing currently supports Facebook pages.")

    try:
        result = publish_facebook_feed_post(
            page_id=account.page_id or account.external_id,
            page_access_token=account.access_token,
            message=post.caption,
        )
        post.status = SocialPost.STATUS_PUBLISHED
        post.published_at = timezone.now()
        post.external_post_id = result.get("id", "")
        post.error_message = ""
        post.save(
            update_fields=[
                "status",
                "published_at",
                "external_post_id",
                "error_message",
                "updated_at",
            ]
        )
        return post
    except Exception as exc:
        post.status = SocialPost.STATUS_FAILED
        post.error_message = str(exc)
        post.save(update_fields=["status", "error_message", "updated_at"])
        raise
