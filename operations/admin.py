from django.contrib import admin
from .models import (
    Appointment, AppointmentAvailability, AuditLog, Contact, CustomerProfile,
    CustomFieldDefinition, Deal, Document, Invitation, Lease, Notification,
    AgentReview, Offer, Owner, Payment, PipelineStage, PublicSubmission,
    SavedProperty, SavedSearch, ScheduledJob, Subscription, SubscriptionPlan, Task,
)

for model in [Contact, Owner, Deal, Offer, Document, Lease, Task, Notification,
              Invitation, CustomFieldDefinition, PipelineStage, AuditLog,
              CustomerProfile, SavedProperty, SavedSearch, AppointmentAvailability,
              Appointment, SubscriptionPlan, Subscription, Payment,
              PublicSubmission, AgentReview, ScheduledJob]:
    admin.site.register(model)
