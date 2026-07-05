from django.contrib import admin
from .models import Agency


@admin.register(Agency)
class AgencyAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "license_number",
        "email",
        "phone",
        "payment_status",
        "created_at",
    )

    search_fields = (
        "name",
        "license_number",
        "email",
        "phone",
        "whatsapp_number",
        "viber_number",
    )