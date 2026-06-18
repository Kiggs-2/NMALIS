from django.contrib import messages
from django.shortcuts import redirect, render

from .decorators import role_required
from .forms import FacilityLicenceApplicationForm, FacilityServicesUpdateForm
from .models import FacilityApplication, StaffAffiliation, User


def _facility_or_redirect(request):
    facility = request.user.facility
    if not facility:
        messages.error(request, "No facility linked to your account.")
        return None
    return facility


def request_email_placeholder(facility):
    admin = facility.admin_users.first()
    return admin.email if admin else ""


@role_required(User.Role.HOSPITAL_ADMIN)
def hospital_apply_licence(request):
    facility = _facility_or_redirect(request)
    if not facility:
        return redirect("dashboard")

    initial = {
        "facility_legal_name": facility.name,
        "registration_number": facility.registration_number,
        "county": facility.county,
        "physical_address": f"{facility.name}, {facility.county}",
        "services_requested": facility.services_offered,
        "accreditation_sought_until": facility.accreditation_expiry,
        "email": request_email_placeholder(facility),
    }
    form = FacilityLicenceApplicationForm(
        request.POST if request.method == "POST" else None,
        request.FILES if request.method == "POST" else None,
        initial=initial if request.method != "POST" else None,
    )
    if request.method == "POST" and form.is_valid():
        app = form.save(commit=False)
        app.facility = facility
        app.application_type = FacilityApplication.ApplicationType.LICENCE_RENEWAL
        app.submitted_by = request.user
        app.save()
        messages.success(
            request,
            "Licence renewal application submitted. KMPDC will review and notify you when processed.",
        )
        return redirect("hospital_facility_profile")

    return render(
        request,
        "registry/hospital_kmpdc_form.html",
        {
            "form": form,
            "form_title": "Application for facility licence renewal",
            "form_subtitle": "Kenya Medical Practitioners and Dentists Council — Form F-ACC-01",
            "back_url": "hospital_facility_profile",
        },
    )


@role_required(User.Role.HOSPITAL_ADMIN)
def hospital_apply_services(request):
    facility = _facility_or_redirect(request)
    if not facility:
        return redirect("dashboard")

    initial = {
        "facility_legal_name": facility.name,
        "registration_number": facility.registration_number,
        "county": facility.county,
        "physical_address": f"{facility.name}, {facility.county}",
        "services_requested": facility.services_offered,
        "accreditation_sought_until": facility.accreditation_expiry,
        "email": request_email_placeholder(facility),
    }
    form = FacilityServicesUpdateForm(
        request.POST if request.method == "POST" else None,
        request.FILES if request.method == "POST" else None,
        initial=initial if request.method != "POST" else None,
    )
    if request.method == "POST" and form.is_valid():
        app = form.save(commit=False)
        app.facility = facility
        app.application_type = FacilityApplication.ApplicationType.SERVICES_UPDATE
        app.submitted_by = request.user
        app.save()
        messages.success(
            request,
            "Services update application submitted. Upon regulator approval, your facility services will update automatically.",
        )
        return redirect("hospital_facility_profile")

    return render(
        request,
        "registry/hospital_kmpdc_form.html",
        {
            "form": form,
            "form_title": "Application for update of services offered",
            "form_subtitle": "Kenya Medical Practitioners and Dentists Council — Form F-SVC-02",
            "back_url": "hospital_facility_profile",
        },
    )


@role_required(User.Role.HOSPITAL_ADMIN)
def hospital_staff_registry(request):
    facility = _facility_or_redirect(request)
    if not facility:
        return redirect("dashboard")

    staff = (
        StaffAffiliation.objects.filter(facility=facility, is_active=True)
        .select_related("practitioner")
        .order_by("practitioner__full_name")
    )
    return render(
        request,
        "registry/hospital_staff_registry.html",
        {"facility": facility, "staff": staff},
    )


@role_required(User.Role.HOSPITAL_ADMIN)
def hospital_personal_doctor(request):
    physician = request.user.personal_physician
    if not physician:
        messages.info(
            request,
            "No personal physician is linked to your account. Contact the system administrator.",
        )
        return redirect("hospital_facility_profile")

    affiliations = physician.affiliations.filter(is_active=True).select_related("facility")
    documents = physician.documents.all().order_by("-submitted_at")[:10]
    return render(
        request,
        "registry/hospital_personal_doctor.html",
        {
            "physician": physician,
            "affiliations": affiliations,
            "documents": documents,
        },
    )
