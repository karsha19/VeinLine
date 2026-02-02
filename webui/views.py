from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.db.models import Count
from django.shortcuts import redirect, render
from django.views.generic import TemplateView
from django.views import View
from django.contrib import messages
from django.db import transaction
import logging

from accounts.models import Profile
from donations.models import BloodBankInventory, DonorDetails
from sos.models import SOSRequest, SOSResponse, SOSStatus, SOSPriority
from sos.services import match_donors_for_request
from core.services.sms import send_sms
from core.services.emailing import send_fallback_email

logger = logging.getLogger(__name__)


class HomeView(TemplateView):
    template_name = "home.html"


class AboutView(TemplateView):
    template_name = "about.html"


class LoginView(View):
    template_name = "auth/login.html"

    def get(self, request):
        if request.user.is_authenticated:
            return redirect("home")
        return render(request, self.template_name)

    def post(self, request):
        username = request.POST.get("username")
        password = request.POST.get("password")
        
        if not username or not password:
            messages.error(request, "Please provide both username and password.")
            return render(request, self.template_name)
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            next_url = request.GET.get("next", "home")
            return redirect(next_url)
        else:
            messages.error(request, "Invalid username or password. Please try again.")
            return render(request, self.template_name)


class RegisterView(View):
    template_name = "auth/register.html"

    def get(self, request):
        if request.user.is_authenticated:
            return redirect("home")
        return render(request, self.template_name)

    def post(self, request):
        username = request.POST.get("username")
        email = request.POST.get("email")
        password = request.POST.get("password")
        password_confirm = request.POST.get("password_confirm")
        role = request.POST.get("role", "donor")
        full_name = request.POST.get("full_name", "")
        phone = request.POST.get("phone", "")
        
        # Validation
        if not username or not email or not password:
            messages.error(request, "Please fill in all required fields.")
            return render(request, self.template_name)
        
        if password != password_confirm:
            messages.error(request, "Passwords do not match.")
            return render(request, self.template_name)
        
        if len(password) < 8:
            messages.error(request, "Password must be at least 8 characters long.")
            return render(request, self.template_name)
        
        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists. Please choose another.")
            return render(request, self.template_name)
        
        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already registered. Please use another email.")
            return render(request, self.template_name)
        
        # Create user
        try:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=full_name.split()[0] if full_name else "",
                last_name=" ".join(full_name.split()[1:]) if len(full_name.split()) > 1 else ""
            )
            
            # Create profile (signals should handle this, but ensure it exists)
            profile, created = Profile.objects.get_or_create(
                user=user,
                defaults={
                    'role': role,
                    'phone_e164': phone if phone else None
                }
            )
            if not created:
                # Update existing profile
                profile.role = role
                if phone:
                    profile.phone_e164 = phone
                profile.save()
            
            # Auto-login (specify backend because multiple auth backends are configured)
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, f"Welcome to VeinLine, {user.username}! Your account has been created successfully.")
            return redirect("home")
        except Exception as e:
            messages.error(request, f"An error occurred: {str(e)}")
            return render(request, self.template_name)


class LogoutViewCustom(View):
    """Custom logout view that handles both GET and POST"""
    def get(self, request):
        logout(request)
        messages.success(request, "You have been logged out successfully.")
        return redirect("home")
    
    def post(self, request):
        logout(request)
        messages.success(request, "You have been logged out successfully.")
        return redirect("home")


class RoleRequiredMixin(LoginRequiredMixin):
    allowed_roles: set[str] = set()

    def dispatch(self, request, *args, **kwargs):
        role = getattr(getattr(request.user, "profile", None), "role", "")
        if request.user.is_staff or role in self.allowed_roles:
            return super().dispatch(request, *args, **kwargs)
        return redirect("home")


class DonorDashboardView(RoleRequiredMixin, TemplateView):
    template_name = "dashboards/donor.html"
    allowed_roles = {"donor"}

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        details = getattr(self.request.user, "donor_details", None)
        ctx["donor_details"] = details
        ctx["pending_responses"] = SOSResponse.objects.filter(donor=self.request.user, response="pending").count()
        ctx["open_sos_nearby"] = (
            SOSRequest.objects.filter(status="open", city__iexact=(details.city if details else ""))
            .order_by("-created_at")[:10]
        )
        return ctx


class PatientDashboardView(RoleRequiredMixin, TemplateView):
    template_name = "dashboards/patient.html"
    allowed_roles = {"patient"}

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        my = SOSRequest.objects.filter(requester=self.request.user).order_by("-created_at")
        ctx["my_requests"] = my[:20]
        ctx["my_open_count"] = my.filter(status="open").count()
        ctx["responses_count"] = SOSResponse.objects.filter(request__requester=self.request.user).count()
        return ctx


class AdminDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboards/admin.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return redirect("home")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["donors_by_group"] = list(
            DonorDetails.objects.values("blood_group").annotate(count=Count("id")).order_by("blood_group")
        )
        ctx["donors_active"] = DonorDetails.objects.filter(is_available=True).count()
        ctx["donors_inactive"] = DonorDetails.objects.filter(is_available=False).count()
        ctx["sos_by_status"] = list(
            SOSRequest.objects.values("status").annotate(count=Count("id")).order_by("status")
        )
        ctx["responses_by_choice"] = list(
            SOSResponse.objects.values("response").annotate(count=Count("id")).order_by("response")
        )
        ctx["inventory"] = BloodBankInventory.objects.all().order_by("city", "blood_group")[:50]
        return ctx


class CreateSOSView(RoleRequiredMixin, TemplateView):
    """Create emergency SOS request"""
    template_name = "create_sos.html"
    allowed_roles = {"patient"}

    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        """Handle SOS creation from form"""
        try:
            blood_group = request.POST.get('blood_group_needed', '').strip()
            units = int(request.POST.get('units_needed', 1))
            city = request.POST.get('city', '').strip()
            area = request.POST.get('area', '').strip()
            hospital = request.POST.get('hospital_name', '').strip()
            message = request.POST.get('message', '').strip()
            priority = request.POST.get('priority', SOSPriority.NORMAL)

            # Validation
            if not blood_group:
                messages.error(request, "Blood group is required.")
                return render(request, self.template_name)
            
            if not city:
                messages.error(request, "City is required.")
                return render(request, self.template_name)

            if units < 1 or units > 10:
                messages.error(request, "Units must be between 1 and 10.")
                return render(request, self.template_name)

            if priority not in dict(SOSPriority.choices):
                priority = SOSPriority.NORMAL

            # Create SOS request
            sos_request = SOSRequest.objects.create(
                requester=request.user,
                blood_group_needed=blood_group,
                units_needed=units,
                city=city,
                area=area,
                hospital_name=hospital,
                message=message,
                status=SOSStatus.OPEN,
                priority=priority,
            )

            messages.success(
                request,
                f"🚨 SOS Request #{sos_request.id} created successfully! "
                f"Looking for matching {blood_group} donors in {city}..."
            )

            # Find and notify matching donors
            try:
                logger.info(f"[SOS #{sos_request.id}] Starting donor matching for {blood_group} in {city}")
                
                donors = match_donors_for_request(sos_request, limit=50)
                donors_list = list(donors)
                
                logger.info(f"[SOS #{sos_request.id}] Found {len(donors_list)} matching donors")
                
                if donors_list:
                    # Send SMS to each donor
                    sms_message = (
                        f"VeinLine SOS: Need {sos_request.blood_group_needed} blood in {sos_request.city}. "
                        f"Reply: YES {sos_request.sms_reply_token} or NO {sos_request.sms_reply_token}."
                    )

                    notified_count = 0
                    failed_count = 0
                    no_phone_count = 0
                    
                    with transaction.atomic():
                        for donor in donors_list:
                            donor_name = donor.user.username
                            
                            # Create response record
                            SOSResponse.objects.get_or_create(
                                request=sos_request,
                                donor=donor.user,
                                defaults={'response': 'pending', 'channel': 'sms'}
                            )

                            # Send SMS
                            phone = getattr(getattr(donor.user, 'profile', None), 'phone_e164', '')
                            if phone:
                                try:
                                    logger.info(f"[SOS #{sos_request.id}] Sending SMS to {donor_name} ({phone})")
                                    result = send_sms(phone, sms_message)
                                    
                                    if result.get('ok'):
                                        logger.info(f"[SOS #{sos_request.id}] ✓ SMS sent to {donor_name}")
                                        notified_count += 1
                                    else:
                                        logger.warning(f"[SOS #{sos_request.id}] ✗ SMS failed for {donor_name}: {result.get('reason')}")
                                        failed_count += 1
                                except Exception as e:
                                    logger.error(f"[SOS #{sos_request.id}] Error sending SMS to {donor_name}: {str(e)}")
                                    failed_count += 1
                            else:
                                logger.warning(f"[SOS #{sos_request.id}] Donor {donor_name} has no phone number")
                                no_phone_count += 1

                            # Email fallback
                            try:
                                send_fallback_email(
                                    to_email=getattr(donor.user, 'email', ''),
                                    subject="VeinLine SOS Alert",
                                    message=sms_message,
                                )
                            except Exception as e:
                                logger.warning(f"[SOS #{sos_request.id}] Error sending email to {donor.user.email}: {str(e)}")

                    summary = f"✅ Found {len(donors_list)} matching donors. "
                    if notified_count > 0:
                        summary += f"Notifications sent to {notified_count}"
                    if no_phone_count > 0:
                        summary += f" ({no_phone_count} donors missing phone)"
                    if failed_count > 0:
                        summary += f" ({failed_count} SMS failures)"
                    
                    logger.info(f"[SOS #{sos_request.id}] Summary: {summary}")
                    messages.success(request, summary)
                else:
                    logger.warning(f"[SOS #{sos_request.id}] No matching donors found for {blood_group} in {city}")
                    messages.warning(
                        request,
                        f"⚠️ No matching donors found in {city} with {blood_group} blood group. "
                        "Check the status regularly - more donors may become available."
                    )

            except Exception as e:
                logger.error(f"[SOS #{sos_request.id}] Error during donor notification: {str(e)}", exc_info=True)
                messages.warning(
                    request,
                    f"SOS created (#{sos_request.id}), but error notifying donors: {str(e)}"
                )

            # Redirect to patient dashboard
            return redirect('patient-dashboard')

        except Exception as e:
            messages.error(request, f"Error creating SOS: {str(e)}")
            return render(request, self.template_name)


class LeaderboardView(TemplateView):
    """Public leaderboard view for donors"""
    template_name = "leaderboard.html"


class AppointmentsView(TemplateView):
    """Appointment booking view"""
    template_name = "appointments.html"


class BloodBanksView(TemplateView):
    """Blood bank finder view"""
    template_name = "blood_banks.html"


class EligibilityCheckerView(TemplateView):
    """Medical eligibility checker view"""
    template_name = "eligibility_checker.html"


class ActivityTimelineView(LoginRequiredMixin, TemplateView):
    """User activity timeline view"""
    template_name = "activity_timeline.html"