from django.urls import path

from .public_views import (
    PublicPropertyListView,
    PublicPropertyDetailView,
    PublicPropertyFilterOptionsView,
    PublicPropertyInquiryView,
    PublicSimilarPropertiesView,
    PublicPropertyEventView,
    PublicPropertyShareDetailView,
    PublicDistributionLinkRedirectView,
)


urlpatterns = [
    path("s/<str:code>/", PublicDistributionLinkRedirectView.as_view(), name="public-distribution-link"),
    path(
        "agencies/by-slug/<slug:slug>/listings/<slug:share_slug>/",
        PublicPropertyShareDetailView.as_view(),
        name="public-property-share-detail",
    ),
    path(
        "agencies/<str:license_number>/properties/",
        PublicPropertyListView.as_view(),
        name="public-property-list"
    ),

    path(
        "agencies/<str:license_number>/properties/filter-options/",
        PublicPropertyFilterOptionsView.as_view(),
        name="public-property-filter-options"
    ),

    path(
        "agencies/<str:license_number>/properties/<int:property_id>/inquire/",
        PublicPropertyInquiryView.as_view(),
        name="public-property-inquiry"
    ),

    path(
        "agencies/<str:license_number>/properties/<int:property_id>/similar/",
        PublicSimilarPropertiesView.as_view(),
        name="public-similar-properties"
    ),

    path(
        "agencies/<str:license_number>/properties/<int:property_id>/events/",
        PublicPropertyEventView.as_view(),
        name="public-property-event"
    ),

    path(
        "agencies/<str:license_number>/properties/<int:pk>/",
        PublicPropertyDetailView.as_view(),
        name="public-property-detail"
    ),
]
