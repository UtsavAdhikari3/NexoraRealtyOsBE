from django.urls import path

from .views import (
    LeadListCreateView,
    LeadDetailView,
    LeadPropertyInterestListCreateView,
    LeadPropertyInterestDetailView,
    LeadInteractionListCreateView,
    LeadInteractionDetailView,
    LeadFollowUpCompleteView,
    LeadTimelineView,
    LeadWorkspaceView,
    LeadDocumentListCreateView,
)


urlpatterns = [
    path(
        "",
        LeadListCreateView.as_view(),
        name="lead-list"
    ),

    path(
        "<int:pk>/",
        LeadDetailView.as_view(),
        name="lead-detail"
    ),

    path(
        "<int:lead_id>/interests/",
        LeadPropertyInterestListCreateView.as_view(),
        name="lead-property-interest-list"
    ),

    path(
        "interests/<int:pk>/",
        LeadPropertyInterestDetailView.as_view(),
        name="lead-property-interest-detail"
    ),

    path(
        "<int:lead_id>/interactions/",
        LeadInteractionListCreateView.as_view(),
        name="lead-interaction-list"
    ),

    path(
        "interactions/<int:pk>/",
        LeadInteractionDetailView.as_view(),
        name="lead-interaction-detail"
    ),
    path(
        "<int:lead_id>/complete-follow-up/",
        LeadFollowUpCompleteView.as_view(),
        name="lead-complete-follow-up",
    ),
    path(
        "<int:lead_id>/timeline/",
        LeadTimelineView.as_view(),
        name="lead-timeline",
    ),
    path(
        "<int:lead_id>/workspace/",
        LeadWorkspaceView.as_view(),
        name="lead-workspace",
    ),
    path(
        "<int:lead_id>/documents/",
        LeadDocumentListCreateView.as_view(),
        name="lead-document-list",
    ),
]
