from django.urls import path

from .views import (
    SiteVisitListCreateView,
    SiteVisitDetailView,
)


urlpatterns = [
    path(
        "",
        SiteVisitListCreateView.as_view(),
        name="site-visit-list"
    ),

    path(
        "<int:pk>/",
        SiteVisitDetailView.as_view(),
        name="site-visit-detail"
    ),
]