from django.urls import path

from .public_views import (
    PublicAgencyContactView,
    PublicAgencyDetailView,
    PublicAgencySlugDetailView,
    PublicAgencyDomainDetailView,
    PublicAgencyPreviewView,
    PublicAgentListView,
    PublicAgentDetailView,
)


urlpatterns = [
    path(
        "agencies/website-preview/",
        PublicAgencyPreviewView.as_view(),
        name="public-agency-website-preview",
    ),
    path(
        "agencies/by-slug/<slug:slug>/",
        PublicAgencySlugDetailView.as_view(),
        name="public-agency-detail-by-slug",
    ),
    path(
        "agencies/by-domain/",
        PublicAgencyDomainDetailView.as_view(),
        name="public-agency-detail-by-domain",
    ),
    path(
        "agencies/<str:license_number>/",
        PublicAgencyDetailView.as_view(),
        name="public-agency-detail"
    ),
    path(
        "agencies/<str:license_number>/agents/",
        PublicAgentListView.as_view(),
        name="public-agent-list",
    ),
    path(
        "agencies/<str:license_number>/agents/<int:pk>/",
        PublicAgentDetailView.as_view(),
        name="public-agent-detail",
    ),
    path(
        "agencies/<str:license_number>/contact/",
        PublicAgencyContactView.as_view(),
        name="public-agency-contact",
    ),
]
