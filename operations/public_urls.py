from django.urls import path
from . import views

urlpatterns = [
    path("agencies/<slug:slug>/submissions/", views.public_submission_create, name="public-submission-create"),
    path("agencies/<slug:slug>/agents/<int:agent_id>/reviews/", views.public_agent_review_create, name="public-agent-review-create"),
    path("agencies/<slug:slug>/customers/", views.customer_register, name="customer-register"),
    path("agencies/<slug:slug>/customers/login/", views.customer_login, name="customer-login"),
    path("agencies/<slug:slug>/customer/saved-properties/", views.customer_saved_properties, name="customer-saved-properties"),
    path("agencies/<slug:slug>/customer/saved-searches/", views.customer_saved_searches, name="customer-saved-searches"),
    path("agencies/<slug:slug>/appointments/", views.public_appointments, name="public-appointments"),
]
