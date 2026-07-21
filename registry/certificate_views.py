from datetime import timedelta
from django.conf import settings as django_settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .certificate_services import (
    facility_can_download,
    pdf_response,
    practitioner_can_download,
)
from .decorators import role_required
from .models import FacilityApplication, FacilityRenewalPayment, HealthcareFacility, PractitionerProfile, User
from .pdf_certificates import build_facility_accreditation_pdf, build_practitioner_license_pdf


PENDING_PAYMENT_TIMEOUT_MINUTES = 30


def _facility_renewal_window_status(facility):
    today = timezone.localdate()
    expiry = facility.accreditation_expiry
    if not expiry:
        return {"can_renew": False, "days_to_expiry": None}
    days_to_expiry = (expiry - today).days
    return {"can_renew": days_to_expiry <= 30, "days_to_expiry": days_to_expiry}


def _cancel_stale_pending_payments(facility):
    cutoff = timezone.now() - timedelta(minutes=PENDING_PAYMENT_TIMEOUT_MINUTES)
    stale_payments = FacilityRenewalPayment.objects.filter(
        facility=facility,
        status=FacilityRenewalPayment.Status.PENDING,
        created_at__lte=cutoff,
    )
    return stale_payments.update(status=FacilityRenewalPayment.Status.FAILED, updated_at=timezone.now())


@role_required(User.Role.REGULATOR, User.Role.PRACTITIONER)
def download_practitioner_certificate(request, pk):
    practitioner = get_object_or_404(PractitionerProfile, pk=pk)
    if not practitioner_can_download(request.user, practitioner):
        raise PermissionDenied("You cannot download this certificate.")
    try:
        buffer = build_practitioner_license_pdf(practitioner)
    except ImportError as exc:
        messages.error(request, str(exc))
        return redirect(request.META.get("HTTP_REFERER", "dashboard"))
    filename = f"practising_licence_{practitioner.license_number}.pdf"
    return pdf_response(buffer, filename)


@role_required(User.Role.REGULATOR, User.Role.HOSPITAL_ADMIN)
def download_facility_certificate(request, pk):
    facility = get_object_or_404(HealthcareFacility, pk=pk)
    if not facility_can_download(request.user, facility):
        raise PermissionDenied("You cannot download this certificate.")
    try:
        buffer = build_facility_accreditation_pdf(facility)
    except ImportError as exc:
        messages.error(request, str(exc))
        return redirect(request.META.get("HTTP_REFERER", "dashboard"))
    filename = f"facility_accreditation_{facility.registration_number}.pdf"
    return pdf_response(buffer, filename)


@role_required(User.Role.PRACTITIONER)
def practitioner_my_license(request):
    profile = request.user.practitioner_profile
    if not profile:
        messages.error(request, "No practitioner profile linked to your account.")
        return redirect("dashboard")
    profile.refresh_compliance_status()
    documents = profile.documents.all().order_by("-submitted_at")
    can_download = practitioner_can_download(request.user, profile)
    return render(
        request,
        "registry/practitioner_my_license.html",
        {
            "profile": profile,
            "documents": documents,
            "can_download": can_download,
        },
    )


@role_required(User.Role.HOSPITAL_ADMIN)
def hospital_facility_profile(request):
    facility = request.user.facility
    if not facility:
        messages.error(request, "No facility linked to your account.")
        return redirect("dashboard")
    _cancel_stale_pending_payments(facility)
    staff = facility.staff_affiliations.filter(is_active=True).select_related("practitioner")
    documents = facility.documents.all().order_by("-submitted_at")
    can_download = facility_can_download(request.user, facility)
    personal_physician = request.user.personal_physician
    recent_applications = facility.applications.select_related("submitted_by").order_by("-created_at")[:5]
    pending_applications = facility.applications.filter(
        status=FacilityApplication.ApplicationStatus.PENDING
    ).count()
    renewal_window = _facility_renewal_window_status(facility)
    return render(
        request,
        "registry/hospital_facility_profile.html",
        {
            "facility": facility,
            "staff": staff,
            "documents": documents,
            "can_download": can_download,
            "personal_physician": personal_physician,
            "recent_applications": recent_applications,
            "pending_applications": pending_applications,
            "renewal_window": renewal_window,
        },
    )
