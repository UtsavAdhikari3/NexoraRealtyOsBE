from django.conf import settings
from django.urls import path

from .views import CurrentAgencyView, TestMarkAgencyPaidView


urlpatterns = [
    path("me/", CurrentAgencyView.as_view(), name="current-agency"),
]

if settings.DEBUG:
    urlpatterns.append(
        path(
            "test/mark-paid/",
            TestMarkAgencyPaidView.as_view(),
            name="test-mark-agency-paid"
        )
    )
