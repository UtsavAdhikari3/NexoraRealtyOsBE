from django.urls import path

from .views import TestMarkAgencyPaidView


urlpatterns = [
    path(
        "test/mark-paid/",
        TestMarkAgencyPaidView.as_view(),
        name="test-mark-agency-paid"
    ),
]