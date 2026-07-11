from django.urls import path

from .public_views import (
    PublicAgencyContactView,
    PublicAgencyDetailView,
    PublicAgencySlugDetailView,
    PublicAgentListView,
)


urlpatterns = [
    path(
        "agencies/<str:license_number>/",
        PublicAgencyDetailView.as_view(),
        name="public-agency-detail"
    ),
    path(
        "agencies/by-slug/<slug:slug>/",
        PublicAgencySlugDetailView.as_view(),
        name="public-agency-detail-by-slug",
    ),
    path(
        "agencies/<str:license_number>/agents/",
        PublicAgentListView.as_view(),
        name="public-agent-list",
    ),
    path(
        "agencies/<str:license_number>/contact/",
        PublicAgencyContactView.as_view(),
        name="public-agency-contact",
    ),
]
