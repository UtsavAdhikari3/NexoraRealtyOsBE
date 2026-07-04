from django.urls import path

from .public_views import PublicAgencyDetailView


urlpatterns = [
    path(
        "agencies/<str:license_number>/",
        PublicAgencyDetailView.as_view(),
        name="public-agency-detail"
    ),
]