from django.urls import path

from .views import (
    PropertyListCreateView,
    PropertyDetailView,
    PropertyMediaListCreateView,
    PropertyMediaDetailView,
    PropertyFilterOptionsView,
    PropertyVerificationDetailView,
    PropertyVerificationDocumentDetailView,
    PropertyFreshnessConfirmView, PropertyRepublishRequestView, PropertyRepublishDecisionView,
    PropertyHistoryListView, PropertyDuplicateFlagListView, PropertyDuplicateFlagDetailView,
    PropertyDistributionToolkitView, PropertyDistributionLinkListCreateView,
    PropertyDistributionLinkDetailView, PropertyDistributionAssetView,
    PropertyPortalExportView, PropertyDistributionSocialDraftView,
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
    path("distribution/portal-export/", PropertyPortalExportView.as_view(), name="property-portal-export"),
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
    path("<int:property_id>/freshness/confirm/", PropertyFreshnessConfirmView.as_view(), name="property-freshness-confirm"),
    path("<int:property_id>/republish/request/", PropertyRepublishRequestView.as_view(), name="property-republish-request"),
    path("<int:property_id>/republish/decision/", PropertyRepublishDecisionView.as_view(), name="property-republish-decision"),
    path("<int:property_id>/history/", PropertyHistoryListView.as_view(), name="property-history-list"),
    path("<int:property_id>/duplicates/", PropertyDuplicateFlagListView.as_view(), name="property-duplicate-list"),
    path("duplicates/<int:pk>/", PropertyDuplicateFlagDetailView.as_view(), name="property-duplicate-detail"),
    path("distribution/links/<int:pk>/", PropertyDistributionLinkDetailView.as_view(), name="property-distribution-link-detail"),
    path("<int:property_id>/distribution/", PropertyDistributionToolkitView.as_view(), name="property-distribution-toolkit"),
    path("<int:property_id>/distribution/links/", PropertyDistributionLinkListCreateView.as_view(), name="property-distribution-links"),
    path("<int:property_id>/distribution/assets/<str:asset_type>/", PropertyDistributionAssetView.as_view(), name="property-distribution-asset"),
    path("<int:property_id>/distribution/social-draft/", PropertyDistributionSocialDraftView.as_view(), name="property-distribution-social-draft"),
]
