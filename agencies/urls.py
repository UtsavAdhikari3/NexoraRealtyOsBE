from django.conf import settings
from django.urls import path

from .views import (
    CurrentAgencyView,
    LocalizationView,
    TestMarkAgencyPaidView,
    WebsiteOnboardingView,
    WebsitePublishView,
    WebsiteUnpublishView,
)


urlpatterns = [
    path("me/", CurrentAgencyView.as_view(), name="current-agency"),
    path("me/website-onboarding/", WebsiteOnboardingView.as_view(), name="website-onboarding"),
    path("me/website/publish/", WebsitePublishView.as_view(), name="website-publish"),
    path("me/website/unpublish/", WebsiteUnpublishView.as_view(), name="website-unpublish"),
    path("localization/", LocalizationView.as_view(), name="agency-localization"),
]

if settings.DEBUG:
    urlpatterns.append(
        path(
            "test/mark-paid/",
            TestMarkAgencyPaidView.as_view(),
            name="test-mark-agency-paid"
        )
    )
