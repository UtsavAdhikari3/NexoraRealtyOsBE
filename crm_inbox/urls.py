from django.urls import path

from .views import (
    ConversationAssignView,
    ConversationCreateLeadView,
    ConversationDetailView,
    ConversationLinkLeadView,
    ConversationListView,
    ConversationMarkReadView,
    ConversationMessagesView,
    ConversationReplyView,
    ConversationStatusView,
)

urlpatterns = [
    path("conversations/", ConversationListView.as_view(), name="inbox-conversation-list"),
    path("conversations/<int:pk>/", ConversationDetailView.as_view(), name="inbox-conversation-detail"),
    path("conversations/<int:conversation_id>/messages/", ConversationMessagesView.as_view(), name="inbox-message-list"),
    path("conversations/<int:conversation_id>/reply/", ConversationReplyView.as_view(), name="inbox-reply"),
    path("conversations/<int:conversation_id>/assign/", ConversationAssignView.as_view(), name="inbox-assign"),
    path("conversations/<int:conversation_id>/link-lead/", ConversationLinkLeadView.as_view(), name="inbox-link-lead"),
    path("conversations/<int:conversation_id>/create-lead/", ConversationCreateLeadView.as_view(), name="inbox-create-lead"),
    path("conversations/<int:conversation_id>/mark-read/", ConversationMarkReadView.as_view(), name="inbox-mark-read"),
    path("conversations/<int:conversation_id>/status/", ConversationStatusView.as_view(), name="inbox-status"),
]
