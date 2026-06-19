from django.contrib import admin
from .models import AgencyUser


@admin.register(AgencyUser)
class AgencyUserAdmin(admin.ModelAdmin):
    list_display = (
        "email",
        "agency",
        "full_name",
        "role",
        "is_staff",
        "is_active",
    )

    search_fields = (
        "email",
        "full_name",
    )