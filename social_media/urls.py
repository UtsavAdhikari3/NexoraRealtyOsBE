from django.urls import path

from .views import (
    SocialPostListCreateView,
    SocialPostDetailView,
    MetaConnectionStartView,
    MetaConnectionCallbackView,
    MetaConnectionSessionView,
    WhatsAppConnectionStartView,
    WhatsAppConnectionCompleteView,
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
    path(
        "connections/whatsapp/start/",
        WhatsAppConnectionStartView.as_view(),
        name="whatsapp-connection-start",
    ),
    path(
        "connections/whatsapp/complete/",
        WhatsAppConnectionCompleteView.as_view(),
        name="whatsapp-connection-complete",
    ),

    path("accounts/", SocialAccountListView.as_view(), name="social-account-list"),
    path("accounts/<int:pk>/disconnect/", SocialAccountDisconnectView.as_view(), name="social-account-disconnect"),
]
