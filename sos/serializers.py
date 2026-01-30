from django.utils import timezone
from rest_framework import serializers

from accounts.models import Profile
from donations.models import DonorDetails
from .models import SOSRequest, SOSResponse


class SOSRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = SOSRequest
        fields = [
            "id",
            "requester",
            "blood_group_needed",
            "units_needed",
            "city",
            "area",
            "hospital_name",
            "message",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "requester", "created_at", "updated_at"]


class DonorPreviewSerializer(serializers.Serializer):
    donor_id = serializers.IntegerField()
    full_name = serializers.CharField()
    blood_group = serializers.CharField()
    city = serializers.CharField()
    area = serializers.CharField(allow_blank=True)
    is_available = serializers.BooleanField()


class SOSResponseSerializer(serializers.ModelSerializer):
    donor_name = serializers.SerializerMethodField()
    donor_blood_group = serializers.SerializerMethodField()
    donor_city = serializers.SerializerMethodField()
    donor_area = serializers.SerializerMethodField()
    donor_phone = serializers.SerializerMethodField()

    class Meta:
        model = SOSResponse
        fields = [
            "id",
            "request",
            "donor",
            "response",
            "channel",
            "donor_consented_to_share_contact",
            "patient_contact_revealed_at",
            "responded_at",
            "created_at",
            # computed
            "donor_name",
            "donor_blood_group",
            "donor_city",
            "donor_area",
            "donor_phone",
        ]
        read_only_fields = [
            "id",
            "request",
            "donor",
            "channel",
            "patient_contact_revealed_at",
            "responded_at",
            "created_at",
            "donor_name",
            "donor_blood_group",
            "donor_city",
            "donor_area",
            "donor_phone",
        ]

    def _donor_details(self, obj) -> DonorDetails | None:
        return getattr(obj.donor, "donor_details", None)

    def get_donor_name(self, obj):
        d = self._donor_details(obj)
        return d.full_name if d else obj.donor.username

    def get_donor_blood_group(self, obj):
        d = self._donor_details(obj)
        return d.blood_group if d else ""

    def get_donor_city(self, obj):
        d = self._donor_details(obj)
        return d.city if d else ""

    def get_donor_area(self, obj):
        d = self._donor_details(obj)
        return d.area if d else ""

    def get_donor_phone(self, obj):
        """
        Privacy rule: phone is hidden unless donor explicitly consents for this request.
        """

        if not obj.donor_consented_to_share_contact:
            return None
        profile: Profile | None = getattr(obj.donor, "profile", None)
        return profile.phone_e164 if profile else None


class RespondSerializer(serializers.Serializer):
    response = serializers.ChoiceField(choices=["yes", "no"])
    consent_to_share_contact = serializers.BooleanField(default=False)

    def save(self, *, sos_response: SOSResponse):
        sos_response.response = self.validated_data["response"]
        sos_response.donor_consented_to_share_contact = bool(self.validated_data["consent_to_share_contact"])
        sos_response.responded_at = timezone.now()
        sos_response.save(update_fields=["response", "donor_consented_to_share_contact", "responded_at"])
        return sos_response


class InboundSMSSerializer(serializers.Serializer):
    """
    Generic inbound webhook body (varies by provider; we normalize).
    """

    from_phone = serializers.CharField()
    message = serializers.CharField()


