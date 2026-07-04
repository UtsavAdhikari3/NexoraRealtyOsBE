from django.urls import path

from .views import TestMarkAgencyPaidView,AgencyProfileView


urlpatterns = [
    path(
        "me/",
        AgencyProfileView.as_view(),
        name="agency-profile"
    ),

    path(
        "test/mark-paid/",
        TestMarkAgencyPaidView.as_view(),
        name="test-mark-agency-paid"
    ),
]