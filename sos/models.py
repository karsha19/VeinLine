import secrets

from django.conf import settings
from django.db import models

from core.constants import BloodGroup


class SOSStatus(models.TextChoices):
    OPEN = "open", "Open"
    FULFILLED = "fulfilled", "Fulfilled"
    CANCELLED = "cancelled", "Cancelled"


class SOSPriority(models.TextChoices):
    NORMAL = "normal", "Normal"
    URGENT = "urgent", "Urgent (24 hours)"
    CRITICAL = "critical", "Critical (Immediate)"


class SOSRequest(models.Model):
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sos_requests")
    blood_group_needed = models.CharField(max_length=3, choices=BloodGroup.CHOICES)
    units_needed = models.PositiveSmallIntegerField(default=1)
    city = models.CharField(max_length=64)
    area = models.CharField(max_length=64, blank=True)
    hospital_name = models.CharField(max_length=120, blank=True)
    message = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=SOSStatus.choices, default=SOSStatus.OPEN)
    priority = models.CharField(max_length=16, choices=SOSPriority.choices, default=SOSPriority.NORMAL)

    # Used for SMS replies without requiring login. Rotatable if abused.
    sms_reply_token = models.CharField(max_length=32, default="", blank=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "blood_group_needed", "city"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["priority", "status"]),
        ]

    def ensure_sms_token(self):
        if not self.sms_reply_token:
            self.sms_reply_token = secrets.token_hex(8)

    def save(self, *args, **kwargs):
        self.ensure_sms_token()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"SOS #{self.id} {self.blood_group_needed} in {self.city} ({self.status})"
    
    def get_priority_icon(self):
        icons = {
            SOSPriority.NORMAL: '🔵',
            SOSPriority.URGENT: '🟠',
            SOSPriority.CRITICAL: '🔴',
        }
        return icons.get(self.priority, '🔵')


class ResponseChoice(models.TextChoices):
    YES = "yes", "Yes"
    NO = "no", "No"
    PENDING = "pending", "Pending"


class ResponseChannel(models.TextChoices):
    WEB = "web", "Web"
    SMS = "sms", "SMS"


class SOSResponse(models.Model):
    request = models.ForeignKey(SOSRequest, on_delete=models.CASCADE, related_name="responses")
    donor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sos_responses")

    response = models.CharField(max_length=16, choices=ResponseChoice.choices, default=ResponseChoice.PENDING)
    channel = models.CharField(max_length=8, choices=ResponseChannel.choices, default=ResponseChannel.WEB)

    # Privacy: contact revealed only after explicit donor consent for this request.
    donor_consented_to_share_contact = models.BooleanField(default=False)
    patient_contact_revealed_at = models.DateTimeField(null=True, blank=True)

    responded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("request", "donor")
        indexes = [
            models.Index(fields=["request", "response"]),
            models.Index(fields=["donor", "response"]),
        ]

    def __str__(self) -> str:
        return f"SOSResponse req={self.request_id} donor={self.donor_id} {self.response}"

# Create your models here.
