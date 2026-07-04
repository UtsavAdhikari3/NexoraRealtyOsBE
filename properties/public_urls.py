from django.urls import path

from .public_views import (
    PublicPropertyListView,
    PublicPropertyDetailView,
    PublicPropertyFilterOptionsView,
)


urlpatterns = [
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
        "agencies/<str:license_number>/properties/<int:pk>/",
        PublicPropertyDetailView.as_view(),
        name="public-property-detail"
    ),
]