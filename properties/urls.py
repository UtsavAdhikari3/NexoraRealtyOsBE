from django.urls import path

from .views import (
    PropertyListCreateView,
    PropertyDetailView,
    PropertyMediaListCreateView,
    PropertyMediaDetailView,
    PropertyFilterOptionsView,
    PropertyVerificationDetailView,
    PropertyVerificationDocumentDetailView,
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
    path(
        "<int:property_id>/verification/",
        PropertyVerificationDetailView.as_view(),
        name="property-verification-detail",
    ),
    path(
        "<int:property_id>/verification/documents/<str:document_type>/",
        PropertyVerificationDocumentDetailView.as_view(),
        name="property-verification-document-detail",
    ),
]
