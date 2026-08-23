from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from django.conf import settings
from django.conf.urls.static import static
from .dashboard import DashboardSummaryView
from .health import HealthCheckView
from crm_inbox.views import MetaWebhookView
from operations.views import stripe_webhook

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("users.urls")),
    path("api/agencies/", include("agencies.urls")),
    path("api/properties/", include("properties.urls")),
    path("api/agents/", include("users.agent_urls")),
    path("api/leads/", include("leads.urls")),
    path("api/site-visits/", include("site_visits.urls")),
    path("api/public/", include("agencies.public_urls")),
    path("api/public/", include("properties.public_urls")),
    path("api/public/", include("site_visits.public_urls")),
    path("api/social-posts/", include("social_media.urls")),
    path("api/inbox/", include("crm_inbox.urls")),
    path("api/operations/", include("operations.urls")),
    path("api/public/", include("operations.public_urls")),
    path("api/webhooks/meta/", MetaWebhookView.as_view(), name="meta-webhook"),
    path("api/webhooks/stripe/", stripe_webhook, name="stripe-webhook"),
    path("api/dashboard/summary/", DashboardSummaryView.as_view(), name="dashboard-summary"),
    path("api/health/", HealthCheckView.as_view(), name="health-check"),
]


if settings.API_DOCS_ENABLED:
    urlpatterns += [
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path(
            "api/docs/",
            SpectacularSwaggerView.as_view(url_name="schema"),
            name="swagger-ui",
        ),
        path(
            "api/redoc/",
            SpectacularRedocView.as_view(url_name="schema"),
            name="redoc",
        ),
    ]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
