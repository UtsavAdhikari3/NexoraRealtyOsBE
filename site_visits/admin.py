from django.contrib import admin

from .models import SiteVisit


@admin.register(SiteVisit)
class SiteVisitAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "lead",
        "property",
        "assigned_agent",
        "scheduled_at",
        "status",
        "agency",
        "created_by",
        "created_at",
    )

    list_filter = (
        "status",
        "scheduled_at",
        "created_at",
    )

    search_fields = (
        "lead__full_name",
        "lead__phone",
        "property__title",
        "notes",
    )