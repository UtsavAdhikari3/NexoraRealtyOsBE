from django.conf import settings
from django.urls import path

from .views import CurrentAgencyView, LocalizationView, TestMarkAgencyPaidView


urlpatterns = [
    path("me/", CurrentAgencyView.as_view(), name="current-agency"),
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
