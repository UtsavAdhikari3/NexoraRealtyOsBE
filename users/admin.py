from django.contrib import admin
from .models import AgencyUser


@admin.register(AgencyUser)
class AgencyUserAdmin(admin.ModelAdmin):
    list_display = ("email", "agency_name", "agency_license_number", "is_active", "is_staff")
    search_fields = ("email", "agency_name", "agency_license_number")
    list_filter = ("is_active", "is_staff")