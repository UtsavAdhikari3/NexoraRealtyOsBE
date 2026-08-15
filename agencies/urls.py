from django.conf import settings
from django.urls import path

from .views import (
    CurrentAgencyView,
    LocalizationView,
    TestMarkAgencyPaidView,
    WebsiteOnboardingView,
    WebsiteMediaView,
    WebsiteValidateView,
    WebsiteCompleteView,
    WebsitePreviewView,
    WebsitePublishView,
    WebsiteUnpublishView,
)


urlpatterns = [
    path("me/", CurrentAgencyView.as_view(), name="current-agency"),
    path("me/website-onboarding/", WebsiteOnboardingView.as_view(), name="website-onboarding"),
    path("me/website-onboarding/media/", WebsiteMediaView.as_view(), name="website-onboarding-media"),
    path("me/website-onboarding/validate/", WebsiteValidateView.as_view(), name="website-onboarding-validate"),
    path("me/website-onboarding/complete/", WebsiteCompleteView.as_view(), name="website-onboarding-complete"),
    path("me/website/preview/", WebsitePreviewView.as_view(), name="website-preview"),
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
