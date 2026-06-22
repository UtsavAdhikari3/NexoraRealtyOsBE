from django.urls import path

from .views import (
    PropertyListCreateView,
    PropertyDetailView,
    PropertyMediaListCreateView,
    PropertyMediaDetailView,
    PropertyFilterOptionsView,
)
urlpatterns = [
    path(
        "",
        PropertyListCreateView.as_view(),
        name="property-list"
    ),

    path(
        "filter-options/",
        PropertyFilterOptionsView.as_view(),
        name="property-filter-options"
    ),

    path(
        "<int:pk>/",
        PropertyDetailView.as_view(),
        name="property-detail"
    ),

    path(
        "<int:property_id>/media/",
        PropertyMediaListCreateView.as_view(),
        name="property-media-list"
    ),

    path(
        "media/<int:pk>/",
        PropertyMediaDetailView.as_view(),
        name="property-media-detail"
    ),
]