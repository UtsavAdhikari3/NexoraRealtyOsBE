from django.contrib import admin

from .models import Lead, LeadPropertyInterest, LeadInteraction


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