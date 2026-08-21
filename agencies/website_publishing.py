from copy import deepcopy

from django.utils import timezone

from .models import Agency, WebsiteVersion
from .website_onboarding import advance_website_draft_revision, materialize_website_config


def publish_website_snapshot(agency: Agency, user, source_version=None):
    """Publish a locked agency draft and append an immutable version row."""
    now = timezone.now()
    published = materialize_website_config(agency)
    next_version = agency.website_config_version + 1
    version = WebsiteVersion.objects.create(
        agency=agency,
        version=next_version,
        template_key=agency.website_template,
        schema_version=published.get("schema_version", 2),
        config=deepcopy(published),
        published_by=user,
        restored_from=source_version,
    )
    agency.website_published_config = deepcopy(published)
    agency.website_config = deepcopy(published)
    agency.website_draft_config = deepcopy(published)
    agency.website_draft_config["accuracy_confirmed"] = False
    revision_fields = advance_website_draft_revision(agency, user)
    agency.website_onboarding_status = Agency.WEBSITE_ONBOARDING_COMPLETED
    agency.website_onboarding_completed_at = now
    agency.website_published_at = now
    agency.is_website_published = True
    agency.website_completion_percentage = 100
    agency.website_config_version = next_version
    agency.save(update_fields=[
        "website_config", "website_published_config", "website_draft_config",
        "website_onboarding_status", "website_onboarding_completed_at",
        "website_published_at", "is_website_published",
        "website_completion_percentage", "website_config_version", *revision_fields,
    ])
    return version
