from django.urls import path

from .views import PublicSiteVisitRequestView


urlpatterns = [
    path(
        "properties/<int:property_id>/request-site-visit/",
        PublicSiteVisitRequestView.as_view(),
        name="public-request-site-visit"
    ),
]