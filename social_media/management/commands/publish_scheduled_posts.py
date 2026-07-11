from django.core.management.base import BaseCommand
from django.utils import timezone

from social_media.models import SocialPost
from social_media.services.publishing import publish_social_post


class Command(BaseCommand):
    help = "Publish due scheduled social posts."

    def handle(self, *args, **options):
        posts = SocialPost.objects.filter(
            status=SocialPost.STATUS_SCHEDULED,
            scheduled_at__lte=timezone.now(),
            social_account__isnull=False,
        ).select_related("social_account")

        published = 0
        failed = 0
        for post in posts.iterator():
            try:
                publish_social_post(post)
                published += 1
            except Exception:
                failed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Published {published} scheduled post(s); {failed} failed."
            )
        )
