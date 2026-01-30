from django.contrib import admin

from .models import Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "phone_e164", "city", "area", "updated_at")
    list_filter = ("role", "city")
    search_fields = ("user__username", "user__email", "phone_e164", "city", "area")
