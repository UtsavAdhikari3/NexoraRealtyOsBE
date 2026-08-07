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
    LeadAutomationSettingsView,
    LeadAssignmentRuleListCreateView,
    LeadAssignmentRuleDetailView,
    LeadDuplicateFlagListView,
    LeadDuplicateFlagReviewView,
    LeadAutomationEventListView,
    LeadAutomationDashboardView,
    LeadAutomationProcessView,
)


urlpatterns = [
    path("automation/settings/", LeadAutomationSettingsView.as_view(), name="lead-automation-settings"),
    path("automation/rules/", LeadAssignmentRuleListCreateView.as_view(), name="lead-automation-rules"),
    path("automation/rules/<int:pk>/", LeadAssignmentRuleDetailView.as_view(), name="lead-automation-rule-detail"),
    path("automation/duplicates/", LeadDuplicateFlagListView.as_view(), name="lead-automation-duplicates"),
    path("automation/duplicates/<int:pk>/", LeadDuplicateFlagReviewView.as_view(), name="lead-automation-duplicate-review"),
    path("automation/events/", LeadAutomationEventListView.as_view(), name="lead-automation-events"),
    path("automation/dashboard/", LeadAutomationDashboardView.as_view(), name="lead-automation-dashboard"),
    path("automation/process/", LeadAutomationProcessView.as_view(), name="lead-automation-process"),
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
