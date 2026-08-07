from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("contacts", views.ContactViewSet, basename="contact")
router.register("owners", views.OwnerViewSet, basename="owner")
router.register("deals", views.DealViewSet, basename="deal")
router.register("offers", views.OfferViewSet, basename="offer")
router.register("documents", views.DocumentViewSet, basename="document")
router.register("leases", views.LeaseViewSet, basename="lease")
router.register("tasks", views.TaskViewSet, basename="task")
router.register("notifications", views.NotificationViewSet, basename="notification")
router.register("invitations", views.InvitationViewSet, basename="invitation")
router.register("team-members", views.TeamMemberViewSet, basename="team-member")
router.register("platform-agencies", views.PlatformAgencyViewSet, basename="platform-agency")
router.register("custom-fields", views.CustomFieldViewSet, basename="custom-field")
router.register("pipeline-stages", views.PipelineStageViewSet, basename="pipeline-stage")
router.register("audit-logs", views.AuditLogViewSet, basename="audit-log")
router.register("availability", views.AppointmentAvailabilityViewSet, basename="availability")
router.register("appointments", views.AppointmentViewSet, basename="appointment")
router.register("subscriptions", views.SubscriptionViewSet, basename="subscription")
router.register("website-submissions", views.PublicSubmissionViewSet, basename="website-submission")
router.register("agent-reviews", views.AgentReviewViewSet, basename="agent-review")

urlpatterns = [
    path("", include(router.urls)),
    path("invitation/accept/", views.accept_invitation, name="invitation-accept"),
    path("reports/summary/", views.report_summary, name="report-summary"),
    path("matching/leads/<int:lead_id>/", views.lead_matches, name="lead-matches"),
    path("properties/compare/", views.compare_properties, name="property-compare"),
    path("admin/summary/", views.admin_summary, name="admin-summary"),
    path("subscription-plans/", views.subscription_plans, name="subscription-plans"),
]
