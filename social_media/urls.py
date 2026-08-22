from django.urls import path

from .views import (
    SocialPostListCreateView,
    SocialPostDetailView,
    MetaConnectionStartView,
    MetaConnectionCallbackView,
    MetaConnectionSessionView,
    SocialAccountListView,
    SocialAccountDisconnectView,
    SocialPostPublishView,
)

urlpatterns = [
    path("posts/", SocialPostListCreateView.as_view(), name="social-post-list-create"),
    path("posts/<int:pk>/", SocialPostDetailView.as_view(), name="social-post-detail"),
    path("posts/<int:pk>/publish/", SocialPostPublishView.as_view(), name="social-post-publish"),

    path("connections/meta/start/", MetaConnectionStartView.as_view(), name="meta-connection-start"),
    path("connections/meta/callback/", MetaConnectionCallbackView.as_view(), name="meta-connection-callback"),
    path(
        "connections/meta/sessions/<str:token>/",
        MetaConnectionSessionView.as_view(),
        name="meta-connection-session",
    ),

    path("accounts/", SocialAccountListView.as_view(), name="social-account-list"),
    path("accounts/<int:pk>/disconnect/", SocialAccountDisconnectView.as_view(), name="social-account-disconnect"),
]
