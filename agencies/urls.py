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
    WebsiteVersionListView,
    WebsiteVersionDetailView,
    WebsiteVersionRestoreView,
    AgencyDomainListCreateView,
    AgencyDomainVerifyView,
    AgencyDomainPrimaryView,
    AgencyDomainDetailView,
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
    path("me/website/versions/", WebsiteVersionListView.as_view(), name="website-version-list"),
    path("me/website/versions/<int:version>/", WebsiteVersionDetailView.as_view(), name="website-version-detail"),
    path("me/website/versions/<int:version>/restore/", WebsiteVersionRestoreView.as_view(), name="website-version-restore"),
    path("me/website/domains/", AgencyDomainListCreateView.as_view(), name="website-domain-list"),
    path("me/website/domains/<int:pk>/", AgencyDomainDetailView.as_view(), name="website-domain-detail"),
    path("me/website/domains/<int:pk>/verify/", AgencyDomainVerifyView.as_view(), name="website-domain-verify"),
    path("me/website/domains/<int:pk>/primary/", AgencyDomainPrimaryView.as_view(), name="website-domain-primary"),
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
