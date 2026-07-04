from django.urls import path

from .views import PublicSiteVisitRequestView


urlpatterns = [
    path(
        "agencies/<str:license_number>/properties/<int:property_id>/request-site-visit/",
        PublicSiteVisitRequestView.as_view(),
        name="public-request-site-visit"
    ),
]