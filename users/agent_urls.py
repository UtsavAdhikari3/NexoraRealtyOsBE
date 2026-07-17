from django.urls import path

from .views import AgentListCreateView, AgentDetailView, AgentSelfProfileView

urlpatterns = [
    path("", AgentListCreateView.as_view(), name="agent-list-create"),
    path("me/profile/", AgentSelfProfileView.as_view(), name="agent-self-profile"),
    path("<int:pk>/", AgentDetailView.as_view(), name="agent-detail"),
]
