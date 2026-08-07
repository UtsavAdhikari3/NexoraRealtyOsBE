from django.contrib import admin

from .models import (
    Lead, LeadPropertyInterest, LeadInteraction, LeadAutomationSettings,
    LeadAssignmentRule, LeadDuplicateFlag, LeadAutomationEvent,
)


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "full_name",
        "phone",
        "source",
        "status",
        "assigned_agent",
        "agency",
        "created_at",
    )

    list_filter = (
        "source",
        "status",
        "purpose",
        "property_type",
        "created_at",
    )

    search_fields = (
        "full_name",
        "phone",
        "email",
        "preferred_location",
    )


@admin.register(LeadPropertyInterest)
class LeadPropertyInterestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "lead",
        "property",
        "interest_level",
        "agency",
        "created_at",
    )

    list_filter = (
        "interest_level",
        "created_at",
    )

    search_fields = (
        "lead__full_name",
        "property__title",
    )


@admin.register(LeadInteraction)
class LeadInteractionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "lead",
        "agent",
        "interaction_type",
        "follow_up_date",
        "agency",
        "created_at",
    )

    list_filter = (
        "interaction_type",
        "follow_up_date",
        "created_at",
    )

    search_fields = (
        "lead__full_name",
        "lead__phone",
        "note",
    )


@admin.register(LeadAutomationSettings)
class LeadAutomationSettingsAdmin(admin.ModelAdmin):
    list_display = ("agency", "is_enabled", "fallback_assignment", "updated_at")


@admin.register(LeadAssignmentRule)
class LeadAssignmentRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "agency", "priority", "assignment_method", "is_active")
    list_filter = ("assignment_method", "is_active")


@admin.register(LeadDuplicateFlag)
class LeadDuplicateFlagAdmin(admin.ModelAdmin):
    list_display = ("lead", "candidate", "score", "status", "created_at")
    list_filter = ("status",)


@admin.register(LeadAutomationEvent)
class LeadAutomationEventAdmin(admin.ModelAdmin):
    list_display = ("lead", "event_type", "from_agent", "to_agent", "created_at")
    list_filter = ("event_type",)
