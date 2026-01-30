from django.contrib import admin

from .models import SOSRequest, SOSResponse


@admin.register(SOSRequest)
class SOSRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "blood_group_needed", "units_needed", "city", "status", "created_at")
    list_filter = ("status", "blood_group_needed", "city")
    search_fields = ("city", "area", "hospital_name", "message")


@admin.register(SOSResponse)
class SOSResponseAdmin(admin.ModelAdmin):
    list_display = ("id", "request", "donor", "response", "channel", "donor_consented_to_share_contact", "created_at")
    list_filter = ("response", "channel", "donor_consented_to_share_contact")
    search_fields = ("donor__username", "donor__email")
