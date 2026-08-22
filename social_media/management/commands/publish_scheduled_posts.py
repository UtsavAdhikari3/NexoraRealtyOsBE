from django.core.management.base import BaseCommand
from django.utils import timezone

from social_media.models import SocialPost
from social_media.services.publishing import publish_social_post
from operations.scheduler import scheduled_job


class Command(BaseCommand):
    help = "Publish due scheduled social posts."

    def handle(self, *args, **options):
        with scheduled_job("social-publishing", lease_seconds=600) as job:
            if not job.claimed:
                self.stdout.write("Social publishing is already running; skipped.")
                return
            result = self.publish_due_posts()
            job.result = result

    def publish_due_posts(self):
        posts = SocialPost.objects.filter(
            status=SocialPost.STATUS_SCHEDULED,
            scheduled_at__lte=timezone.now(),
            social_account__isnull=False,
        ).select_related("social_account")

        published = 0
        partial = 0
        failed = 0
        for post in posts.iterator():
            try:
                publish_social_post(post)
                post.refresh_from_db(fields=["status"])
                if post.status == SocialPost.STATUS_PUBLISHED:
                    published += 1
                elif post.status == SocialPost.STATUS_PARTIAL:
                    partial += 1
                else:
                    failed += 1
            except Exception:
                failed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Published {published} scheduled post(s); "
                f"{partial} partially published; {failed} failed."
            )
        )
        return {"published": published, "partial": partial, "failed": failed}
