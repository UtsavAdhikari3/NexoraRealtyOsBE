from django.urls import path

from .views import AgentListCreateView, AgentDetailView

urlpatterns = [
    path("", AgentListCreateView.as_view(), name="agent-list-create"),
    path("<int:pk>/", AgentDetailView.as_view(), name="agent-detail"),
]