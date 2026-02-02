from django.urls import path

from .views import (
    AboutView, AdminDashboardView, DonorDashboardView, HomeView, LoginView, 
    PatientDashboardView, RegisterView, LeaderboardView, AppointmentsView, 
    BloodBanksView, EligibilityCheckerView, ActivityTimelineView, LogoutViewCustom,
    CreateSOSView
)

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("about/", AboutView.as_view(), name="about"),
    path("leaderboard/", LeaderboardView.as_view(), name="leaderboard"),
    path("appointments/", AppointmentsView.as_view(), name="appointments"),
    path("blood-banks/", BloodBanksView.as_view(), name="blood-banks"),
    path("eligibility/", EligibilityCheckerView.as_view(), name="eligibility"),
    path("timeline/", ActivityTimelineView.as_view(), name="timeline"),
    path("login/", LoginView.as_view(), name="login"),
    path("register/", RegisterView.as_view(), name="register"),
    path("logout/", LogoutViewCustom.as_view(), name="logout"),
    path("dashboard/donor/", DonorDashboardView.as_view(), name="donor-dashboard"),
    path("dashboard/patient/", PatientDashboardView.as_view(), name="patient-dashboard"),
    path("dashboard/admin/", AdminDashboardView.as_view(), name="admin-dashboard"),
    path("sos/create/", CreateSOSView.as_view(), name="create_sos"),
]


