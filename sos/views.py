from __future__ import annotations

import re

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.permissions import IsDonor, IsPatient
from core.services.emailing import send_fallback_email
from core.services.sms import send_sms
from donations.models import DonorDetails
from .models import ResponseChannel, ResponseChoice, SOSRequest, SOSResponse
from .serializers import (
    InboundSMSSerializer,
    RespondSerializer,
    SOSRequestSerializer,
    SOSResponseSerializer,
)
from .services import match_donors_for_request

User = get_user_model()


def _normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D+", "", phone or "")
    return digits


def _find_user_by_phone(phone: str) -> User | None:
    """
    Best-effort matching by last 10 digits (works for many local formats).
    For production, enforce E.164 in registration and compare exact.
    """

    digits = _normalize_phone(phone)
    if not digits:
        return None
    last10 = digits[-10:]
    return User.objects.filter(profile__phone_e164__endswith=last10).first()


class SOSRequestViewSet(viewsets.ModelViewSet):
    serializer_class = SOSRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return SOSRequest.objects.all().order_by("-created_at")
        # Patients see their own requests; donors can see open requests in their city for awareness.
        role = getattr(getattr(user, "profile", None), "role", "")
        if role == "patient":
            return SOSRequest.objects.filter(requester=user).order_by("-created_at")
        if role == "donor":
            city = getattr(getattr(user, "donor_details", None), "city", "")
            qs = SOSRequest.objects.filter(status="open").order_by("-created_at")
            if city:
                qs = qs.filter(city__iexact=city)
            return qs
        return SOSRequest.objects.none()

    def perform_create(self, serializer):
        serializer.save(requester=self.request.user)

    def get_permissions(self):
        if self.action in {"create", "update", "partial_update", "destroy"}:
            return [permissions.IsAuthenticated(), IsPatient()]
        return super().get_permissions()

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated, IsPatient])
    def match(self, request, pk=None):
        """
        Rule-based matching + notifications:
        - Create pending SOSResponse rows for matched donors
        - Send SMS alerts (and email fallback if available)
        """

        sos_req: SOSRequest = self.get_object()
        donors = match_donors_for_request(sos_req, limit=50)

        notified = []
        with transaction.atomic():
            for d in donors:
                resp, created = SOSResponse.objects.get_or_create(
                    request=sos_req,
                    donor=d.user,
                    defaults={"response": ResponseChoice.PENDING, "channel": ResponseChannel.SMS},
                )
                notified.append({"donor_id": d.user_id, "created": created, "response_id": resp.id})

        # Notification message includes token for SMS reply.
        sms_message = (
            f"VeinLine SOS: Need {sos_req.blood_group_needed} blood in {sos_req.city}. "
            f"Reply: YES {sos_req.sms_reply_token} or NO {sos_req.sms_reply_token}."
            f" (Optional consent: YES SHARE {sos_req.sms_reply_token})"
        )

        sms_results = []
        for d in donors:
            phone = getattr(getattr(d.user, "profile", None), "phone_e164", "")
            if phone:
                sms_results.append({"donor_id": d.user_id, "sms": send_sms(phone, sms_message)})
            # Email fallback (if donor has email)
            send_fallback_email(
                to_email=getattr(d.user, "email", ""),
                subject="VeinLine SOS Alert",
                message=sms_message,
            )

        return Response(
            {
                "request_id": sos_req.id,
                "matched_donors": donors.count() if hasattr(donors, "count") else len(donors),
                "responses_created_or_found": notified,
                "sms_results": sms_results,
            }
        )


class SOSResponseViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SOSResponseSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return SOSResponse.objects.select_related("request", "donor").all().order_by("-created_at")
        role = getattr(getattr(user, "profile", None), "role", "")
        if role == "patient":
            return SOSResponse.objects.select_related("request", "donor").filter(request__requester=user).order_by(
                "-created_at"
            )
        if role == "donor":
            return SOSResponse.objects.select_related("request", "donor").filter(donor=user).order_by("-created_at")
        return SOSResponse.objects.none()

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated, IsDonor])
    def respond(self, request, pk=None):
        """
        Donor responds (YES/NO) and may optionally consent to share contact for this request.
        """

        sos_resp: SOSResponse = self.get_object()
        if sos_resp.donor_id != request.user.id and not request.user.is_staff:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        ser = RespondSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ser.save(sos_response=sos_resp)
        return Response(SOSResponseSerializer(sos_resp, context={"request": request}).data)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated, IsPatient])
    def reveal_contact(self, request, pk=None):
        """
        Patient "reveals" contact if donor consented; we track reveal timestamp.
        """

        sos_resp: SOSResponse = self.get_object()
        if sos_resp.request.requester_id != request.user.id and not request.user.is_staff:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        if not sos_resp.donor_consented_to_share_contact:
            return Response({"detail": "Donor has not consented to share contact yet."}, status=400)

        sos_resp.patient_contact_revealed_at = timezone.now()
        sos_resp.save(update_fields=["patient_contact_revealed_at"])
        return Response(SOSResponseSerializer(sos_resp, context={"request": request}).data)


class InboundSMSViewSet(viewsets.ViewSet):
    """
    Provider webhook for SMS replies. Keep it simple: accept normalized JSON.
    You can configure Fast2SMS/Textlocal to call this endpoint, or a small proxy.
    """

    permission_classes = [permissions.AllowAny]

    @action(detail=False, methods=["post"], url_path="inbound")
    def inbound(self, request):
        ser = InboundSMSSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        from_phone = ser.validated_data["from_phone"]
        message = ser.validated_data["message"].strip().upper()

        # Parse: YES <token> | NO <token> | YES SHARE <token>
        parts = re.split(r"\s+", message)
        if not parts:
            return Response({"ok": False, "error": "empty_message"}, status=400)

        decision = parts[0]
        wants_share = "SHARE" in parts[1:-1] if len(parts) >= 3 else False
        token = parts[-1] if len(parts) >= 2 else ""

        if decision not in {"YES", "NO"} or not token:
            return Response({"ok": False, "error": "invalid_format"}, status=400)

        sos_req = SOSRequest.objects.filter(sms_reply_token=token).first()
        if not sos_req:
            return Response({"ok": False, "error": "invalid_token"}, status=404)

        user = _find_user_by_phone(from_phone)
        if not user:
            return Response({"ok": False, "error": "unknown_phone"}, status=404)

        # Ensure donor has donor details (role safety)
        if not hasattr(user, "donor_details"):
            return Response({"ok": False, "error": "not_a_donor"}, status=400)

        sos_resp, _ = SOSResponse.objects.get_or_create(
            request=sos_req,
            donor=user,
            defaults={"response": ResponseChoice.PENDING, "channel": ResponseChannel.SMS},
        )

        sos_resp.response = ResponseChoice.YES if decision == "YES" else ResponseChoice.NO
        sos_resp.channel = ResponseChannel.SMS
        sos_resp.responded_at = timezone.now()
        if wants_share and decision == "YES":
            sos_resp.donor_consented_to_share_contact = True
        sos_resp.save(
            update_fields=["response", "channel", "responded_at", "donor_consented_to_share_contact"]
        )

        return Response({"ok": True, "request_id": sos_req.id, "response_id": sos_resp.id, "response": sos_resp.response})

from django.shortcuts import render

# Create your views here.
