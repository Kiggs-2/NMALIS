from django.contrib.auth import views as auth_views
from django.urls import path

from . import certificate_views, hospital_views, views

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("login/", views.NMALISLoginView.as_view(), name="login"),
    path("logout/", views.logout_view, name="logout"),
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
    path(
        "change-password/",
        auth_views.PasswordChangeView.as_view(
            template_name="registration/password_change_form.html"
        ),
        name="change_password",
    ),
    path(
        "change-password/done/",
        auth_views.PasswordChangeDoneView.as_view(
            template_name="registration/password_change_done.html"
        ),
        name="password_change_done",
    ),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("verify/doctor/", views.verify_doctor, name="verify_doctor"),
    path("verify/hospital/", views.verify_hospital, name="verify_hospital"),
    path("regulator/practitioners/", views.regulator_practitioners, name="regulator_practitioners"),
    path("regulator/facilities/", views.regulator_facilities, name="regulator_facilities"),
    path("regulator/documents/", views.regulator_documents, name="regulator_documents"),
    path("regulator/documents/<int:pk>/", views.regulator_document_review, name="regulator_document_review"),
    path("documents/<int:pk>/preview/", views.document_preview, name="document_preview"),
    path("regulator/practitioners/<int:pk>/", views.regulator_practitioner_detail, name="regulator_practitioner_detail"),
    path("regulator/facilities/<int:pk>/", views.regulator_facility_detail, name="regulator_facility_detail"),
    path("regulator/account/", views.regulator_account, name="regulator_account"),
    path("regulator/analytics/", views.compliance_analytics, name="compliance_analytics"),
    path("regulator/applications/", views.regulator_applications, name="regulator_applications"),
    path(
        "regulator/applications/<int:pk>/",
        views.regulator_application_review,
        name="regulator_application_review",
    ),
    path("regulator/audit/", views.audit_trail, name="audit_trail"),
    path(
        "certificates/practitioner/<int:pk>/download/",
        certificate_views.download_practitioner_certificate,
        name="download_practitioner_certificate",
    ),
    path(
        "certificates/facility/<int:pk>/download/",
        certificate_views.download_facility_certificate,
        name="download_facility_certificate",
    ),
    path("practitioner/my-licence/", certificate_views.practitioner_my_license, name="practitioner_my_license"),
    path("hospital/facility/", certificate_views.hospital_facility_profile, name="hospital_facility_profile"),
    path("hospital/apply-licence/", hospital_views.hospital_apply_licence, name="hospital_apply_licence"),
    path("hospital/apply-services/", hospital_views.hospital_apply_services, name="hospital_apply_services"),
    path("hospital/staff/", hospital_views.hospital_staff_registry, name="hospital_staff_registry"),
    path("hospital/personal-doctor/", hospital_views.hospital_personal_doctor, name="hospital_personal_doctor"),
    path("practitioner/account/", views.practitioner_account, name="practitioner_account"),
    path("hospital/account/", views.hospital_account, name="hospital_account"),
    path("renewal/facility/", views.facility_renewal, name="facility_renewal"),
    path("renewal/practitioner/", views.practitioner_renewal, name="practitioner_renewal"),
    path("alerts/<int:pk>/read/", views.mark_alert_read, name="mark_alert_read"),
    path("support/submit/", views.submit_support_ticket, name="submit_ticket"),
    path("support/my-tickets/", views.my_support_tickets, name="my_tickets"),
]
