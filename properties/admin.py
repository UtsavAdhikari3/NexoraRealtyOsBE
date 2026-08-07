from django.contrib import admin

from .models import PropertyDistributionLink

# Register your models here.


@admin.register(PropertyDistributionLink)
class PropertyDistributionLinkAdmin(admin.ModelAdmin):
    list_display = (
        "code", "property", "source", "medium", "click_count", "is_active", "created_at"
    )
    list_filter = ("source", "medium", "is_active")
    search_fields = ("code", "property__title", "label", "campaign")
