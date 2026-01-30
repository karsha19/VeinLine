from django.conf import settings
from django.db import models


class UserRole(models.TextChoices):
    DONOR = "donor", "Donor"
    PATIENT = "patient", "Patient"
    ADMIN = "admin", "Admin"


class Profile(models.Model):
    """
    Extends Django's auth User with VeinLine-specific attributes and role.
    """

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=16, choices=UserRole.choices, default=UserRole.PATIENT)
    phone_e164 = models.CharField(
        max_length=20,
        blank=True,
        help_text="Phone number in E.164 format (+countrycode...). Stored but not exposed without consent.",
    )
    city = models.CharField(max_length=64, blank=True)
    area = models.CharField(max_length=64, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.user.username} ({self.role})"

# Create your models here.
