import mimetypes
import json

from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.views import LoginView
from django.db.models import Count, Q
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView
from django.views.decorators.csrf import csrf_exempt

from .decorators import role_required
from .analytics import build_compliance_analytics
from .application_services import approve_facility_application, approve_practitioner_application, reject_facility_application, reject_practitioner_application
from .forms import (
    CredibilityCheckForm,
    DocumentReviewForm,
    FacilityApplicationReviewForm,
    FacilityRenewalForm,
    LoginForm,
    PractitionerLicenceRenewalForm,
)
from .models import (
    ComplianceAlert,
    FacilityApplication,
    FacilityRenewalPayment,
    HealthcareFacility,
    LicenseStatus,
    PractitionerProfile,
    PractitionerRenewalApplication,
    PractitionerRenewalPayment,
    RegistryDocument,
    StaffAffiliation,
    StatusChangeLog,
    User,
    VerificationCheck,
    status_badge_color,
    status_label,
)
from .document_utils import (
    annotate_facility_list,
    annotate_practitioner_list,
    build_dossier_context,
    group_documents_by_subject,
    review_registry_document,
)
from .services import (
    derive_facility_status,
    derive_practitioner_status,
    refresh_subject_statuses,
    run_compliance_scan,
    verify_facility,
    verify_practitioner,
)
from . import mpesa as mpesa_client


class HomeView(TemplateView):
    template_name = "registry/home.html"


class NMALISLoginView(LoginView):
    template_name = "registry/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


def logout_view(request):
    logout(request)
    return redirect("home")


@role_required(User.Role.REGULATOR, User.Role.HOSPITAL_ADMIN, User.Role.PRACTITIONER, User.Role.SYSTEM_ADMIN)
def dashboard(request):
    role = request.user.role
    if role == User.Role.SYSTEM_ADMIN:
        return redirect("sysadmin_dashboard")
    if role == User.Role.REGULATOR:
        return _regulator_dashboard(request)
    if role == User.Role.HOSPITAL_ADMIN:
        return _hospital_dashboard(request)
    return _practitioner_dashboard(request)


def _regulator_dashboard(request):
    run_compliance_scan()
    pending_documents = RegistryDocument.objects.filter(
        review_status=RegistryDocument.ReviewStatus.PENDING
    ).count()
    pending_facility_applications = FacilityApplication.objects.filter(
        status=FacilityApplication.ApplicationStatus.PENDING
    ).count()
    pending_practitioner_applications = PractitionerRenewalApplication.objects.filter(
        status=PractitionerRenewalApplication.ApplicationStatus.PENDING
    ).count()
    ctx = {
        "practitioner_count": PractitionerProfile.objects.count(),
        "facility_count": HealthcareFacility.objects.count(),
        "pending_documents": pending_documents,
        "pending_applications": pending_facility_applications + pending_practitioner_applications,
        "pending_facility_applications": pending_facility_applications,
        "pending_practitioner_applications": pending_practitioner_applications,
        "suspended_practitioners": PractitionerProfile.objects.filter(
            status__in=[LicenseStatus.SUSPENDED, LicenseStatus.REVOKED]
        ).count(),
        "non_compliant_facilities": HealthcareFacility.objects.exclude(status=LicenseStatus.ACTIVE).count(),
        "recent_logs": StatusChangeLog.objects.select_related("changed_by")[:8],
        "recent_documents": RegistryDocument.objects.select_related(
            "practitioner", "facility"
        ).filter(review_status=RegistryDocument.ReviewStatus.PENDING)[:5],
        "status_breakdown": [
            {
                "label": status_label(row["status"]),
                "status": row["status"],
                "color": status_badge_color(row["status"]),
                "c": row["c"],
            }
            for row in PractitionerProfile.objects.values("status").annotate(c=Count("id"))
        ],
    }
    return render(request, "registry/dashboard_regulator.html", ctx)


def _hospital_dashboard(request):
    facility = request.user.facility
    staff = []
    alerts = ComplianceAlert.objects.filter(recipient=request.user, is_read=False)[:10]
    if facility:
        staff = (
            StaffAffiliation.objects.filter(facility=facility, is_active=True)
            .select_related("practitioner")
        )
    ctx = {
        "facility": facility,
        "staff": staff,
        "alerts": alerts,
        "recent_checks": VerificationCheck.objects.filter(performed_by=request.user)[:5],
    }
    return render(request, "registry/dashboard_hospital.html", ctx)


def _practitioner_dashboard(request):
    profile = request.user.practitioner_profile
    if profile:
        profile.refresh_compliance_status()
    alerts = ComplianceAlert.objects.filter(recipient=request.user, is_read=False)[:10]
    affiliations = []
    if profile:
        affiliations = profile.affiliations.filter(is_active=True).select_related("facility")
    ctx = {
        "profile": profile,
        "alerts": alerts,
        "affiliations": affiliations,
        "recent_checks": VerificationCheck.objects.filter(performed_by=request.user)[:5],
    }
    return render(request, "registry/dashboard_practitioner.html", ctx)


@role_required(User.Role.REGULATOR)
def regulator_account(request):
    user = request.user
    return render(
        request,
        "registry/regulator_account.html",
        {
            "user": user,
            "facility": user.facility,
        },
    )


@role_required(User.Role.PRACTITIONER)
def practitioner_account(request):
    user = request.user
    profile = user.practitioner_profile
    return render(
        request,
        "registry/practitioner_account.html",
        {"user": user, "profile": profile},
    )


@role_required(User.Role.HOSPITAL_ADMIN)
def hospital_account(request):
    user = request.user
    facility = user.facility
    personal_physician = user.personal_physician
    pending_apps = 0
    if facility:
        pending_apps = facility.applications.filter(
            status=FacilityApplication.ApplicationStatus.PENDING
        ).count()
    return render(
        request,
        "registry/hospital_account.html",
        {
            "user": user,
            "facility": facility,
            "personal_physician": personal_physician,
            "pending_apps": pending_apps,
        },
    )


@role_required(User.Role.HOSPITAL_ADMIN)
def verify_doctor(request):
    result = None
    form = CredibilityCheckForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        result = verify_practitioner(form.cleaned_data["identifier"], request.user)
    return render(
        request,
        "registry/verify.html",
        {
            "form": form,
            "result": result,
            "title": "Doctor Credibility Check",
            "subtitle": "Verify a practitioner's standing against the national registry.",
        },
    )


@role_required(User.Role.PRACTITIONER)
def verify_hospital(request):
    result = None
    form = CredibilityCheckForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        result = verify_facility(form.cleaned_data["identifier"], request.user)
    return render(
        request,
        "registry/verify.html",
        {
            "form": form,
            "result": result,
            "title": "Hospital Credibility Check",
            "subtitle": "Verify a facility's accreditation before employment.",
        },
    )


@role_required(User.Role.REGULATOR)
def regulator_practitioners(request):
    q = request.GET.get("q", "").strip()
    qs = annotate_practitioner_list(PractitionerProfile.objects.all())
    if q:
        qs = qs.filter(Q(license_number__icontains=q) | Q(full_name__icontains=q))
    return render(request, "registry/regulator_list.html", {"items": qs, "entity": "practitioner", "q": q})


@role_required(User.Role.REGULATOR)
def regulator_facilities(request):
    q = request.GET.get("q", "").strip()
    qs = annotate_facility_list(HealthcareFacility.objects.all())
    if q:
        qs = qs.filter(Q(registration_number__icontains=q) | Q(name__icontains=q))
    return render(request, "registry/regulator_list.html", {"items": qs, "entity": "facility", "q": q})


@role_required(User.Role.REGULATOR)
def regulator_documents(request):
    status_filter = request.GET.get("status", RegistryDocument.ReviewStatus.PENDING)
    doc_type = request.GET.get("type", "")
    q = request.GET.get("q", "").strip()

    documents = RegistryDocument.objects.select_related("practitioner", "facility", "reviewed_by")
    if status_filter:
        documents = documents.filter(review_status=status_filter)
    if doc_type:
        documents = documents.filter(document_type=doc_type)
    if q:
        documents = documents.filter(
            Q(title__icontains=q)
            | Q(reference_number__icontains=q)
            | Q(practitioner__full_name__icontains=q)
            | Q(practitioner__license_number__icontains=q)
            | Q(facility__name__icontains=q)
            | Q(facility__registration_number__icontains=q)
        )

    documents = documents.order_by(
        "practitioner__full_name",
        "facility__name",
        "document_type",
        "-submitted_at",
    )[:200]
    subject_groups = group_documents_by_subject(documents)

    return render(
        request,
        "registry/regulator_documents.html",
        {
            "subject_groups": subject_groups,
            "status_filter": status_filter,
            "doc_type": doc_type,
            "q": q,
            "document_types": RegistryDocument.DocumentType.choices,
            "review_statuses": RegistryDocument.ReviewStatus.choices,
        },
    )


@role_required(User.Role.REGULATOR)
def regulator_document_review(request, pk):
    refresh_subject_statuses(triggered_by=request.user)
    document = get_object_or_404(
        RegistryDocument.objects.select_related("practitioner", "facility"),
        pk=pk,
    )
    is_locked = document.review_status != RegistryDocument.ReviewStatus.PENDING
    form = None if is_locked else DocumentReviewForm(request.POST if request.method == "POST" else None)
    if not is_locked and request.method == "POST" and form.is_valid():
        review_registry_document(document, form, request.user)
        messages.success(request, f"Document marked as {document.get_review_status_display()}.")
        return _redirect_to_document_dossier(document)

    return render(
        request,
        "registry/regulator_document_review.html",
        {"document": document, "form": form, "is_locked": is_locked},
    )


@role_required(User.Role.REGULATOR, User.Role.HOSPITAL_ADMIN, User.Role.PRACTITIONER)
def document_preview(request, pk):
    document = get_object_or_404(
        RegistryDocument.objects.select_related("practitioner", "facility"),
        pk=pk,
    )
    if request.user.role != User.Role.REGULATOR:
        if request.user.role == User.Role.PRACTITIONER:
            if not document.practitioner_id or request.user.practitioner_profile_id != document.practitioner_id:
                return redirect("dashboard")
        elif request.user.role == User.Role.HOSPITAL_ADMIN:
            if not document.facility_id or request.user.facility_id != document.facility_id:
                return redirect("dashboard")

    if not document.file:
        messages.error(request, "No file is attached to this document.")
        return redirect("dashboard")

    content_type = mimetypes.guess_type(document.file.name)[0] or "application/octet-stream"
    response = FileResponse(document.file.open("rb"), content_type=content_type)
    response["Content-Disposition"] = f'inline; filename="{document.file.name.split("/")[-1]}"'
    return response


def _redirect_to_document_dossier(document: RegistryDocument):
    if document.practitioner_id:
        return redirect("regulator_practitioner_detail", pk=document.practitioner_id)
    if document.facility_id:
        return redirect("regulator_facility_detail", pk=document.facility_id)
    return redirect("regulator_documents")


def _handle_dossier_review(request, documents_queryset):
    document_id = request.POST.get("document_id")
    document = get_object_or_404(documents_queryset, pk=document_id)
    is_locked = document.review_status != RegistryDocument.ReviewStatus.PENDING
    if is_locked:
        messages.info(request, "This document has already been reviewed and cannot be changed.")
        return redirect(f"{request.path}#doc-{document.pk}"), build_dossier_context(documents_queryset)
    form = DocumentReviewForm(request.POST, prefix=f"doc_{document.pk}")
    if form.is_valid():
        review_registry_document(document, form, request.user)
        messages.success(request, f"“{document.title}” marked as {document.get_review_status_display()}.")
        return redirect(f"{request.path}#doc-{document.pk}"), None
    dossier = build_dossier_context(documents_queryset, open_document_id=document.pk)
    for row in dossier["document_rows"]:
        if row["document"].pk == document.pk:
            row["form"] = form
            row["is_open"] = True
            break
    return None, dossier


@role_required(User.Role.REGULATOR)
def regulator_practitioner_detail(request, pk):
    refresh_subject_statuses(triggered_by=request.user)
    practitioner = get_object_or_404(PractitionerProfile, pk=pk)
    documents_qs = practitioner.documents.select_related("reviewed_by").order_by("document_type", "-submitted_at")
    applications_qs = practitioner.renewal_applications.select_related("reviewed_by").order_by("-submitted_at")

    derived_status = derive_practitioner_status(practitioner)
    dossier = build_dossier_context(documents_qs)

    application_review_form = None
    review_application = None
    review_type = request.POST.get("review_type") if request.method == "POST" else None

    if request.method == "POST" and review_type == "application":
        app_pk = request.POST.get("application_pk")
        review_application = get_object_or_404(applications_qs, pk=app_pk)
        is_locked = review_application.status != PractitionerRenewalApplication.ApplicationStatus.PENDING
        if not is_locked:
            application_review_form = FacilityApplicationReviewForm(request.POST)
            if application_review_form.is_valid():
                decision = application_review_form.cleaned_data["decision"]
                notes = application_review_form.cleaned_data.get("review_notes", "")
                if decision == "approved":
                    approve_practitioner_application(review_application, request.user)
                    messages.success(request, "Practitioner renewal approved.")
                else:
                    reject_practitioner_application(review_application, request.user, notes)
                    messages.warning(request, "Practitioner renewal rejected.")
                return redirect("regulator_practitioner_detail", pk=practitioner.pk)
        else:
            messages.info(request, "This application has already been reviewed.")
            return redirect("regulator_practitioner_detail", pk=practitioner.pk)
    elif request.method == "POST":
        response, dossier_override = _handle_dossier_review(request, documents_qs)
        if response is not None:
            return response
        dossier = dossier_override
        derived_status = derive_practitioner_status(practitioner)

    logs = StatusChangeLog.objects.filter(entity_type="practitioner", entity_id=practitioner.pk)[:10]
    return render(
        request,
        "registry/regulator_practitioner_detail.html",
        {
            "practitioner": practitioner,
            "derived_status": derived_status,
            "logs": logs,
            "applications": applications_qs,
            "application_review_form": application_review_form,
            "review_application": review_application,
            **dossier,
        },
    )


@role_required(User.Role.REGULATOR)
def regulator_facility_detail(request, pk):
    refresh_subject_statuses(triggered_by=request.user)
    facility = get_object_or_404(HealthcareFacility, pk=pk)
    documents_qs = facility.documents.select_related("reviewed_by").order_by("document_type", "-submitted_at")
    applications_qs = facility.applications.select_related("submitted_by", "reviewed_by").order_by("-created_at")

    derived_status = derive_facility_status(facility)
    dossier = build_dossier_context(documents_qs)

    application_review_form = None
    review_application = None
    review_type = request.POST.get("review_type") if request.method == "POST" else None

    if request.method == "POST" and review_type == "application":
        app_pk = request.POST.get("application_pk")
        review_application = get_object_or_404(applications_qs, pk=app_pk)
        is_locked = review_application.status != FacilityApplication.ApplicationStatus.PENDING
        if not is_locked:
            application_review_form = FacilityApplicationReviewForm(request.POST)
            if application_review_form.is_valid():
                decision = application_review_form.cleaned_data["decision"]
                notes = application_review_form.cleaned_data.get("review_notes", "")
                if decision == "approved":
                    approve_facility_application(review_application, request.user)
                    messages.success(request, "Facility application approved.")
                else:
                    reject_facility_application(review_application, request.user, notes)
                    messages.warning(request, "Facility application rejected.")
                return redirect("regulator_facility_detail", pk=facility.pk)
        else:
            messages.info(request, "This application has already been reviewed.")
            return redirect("regulator_facility_detail", pk=facility.pk)
    elif request.method == "POST":
        response, dossier_override = _handle_dossier_review(request, documents_qs)
        if response is not None:
            return response
        dossier = dossier_override
        derived_status = derive_facility_status(facility)

    staff = StaffAffiliation.objects.filter(facility=facility, is_active=True).select_related("practitioner")
    logs = StatusChangeLog.objects.filter(entity_type="facility", entity_id=facility.pk)[:10]
    approved_services_update = facility.applications.filter(
        application_type=FacilityApplication.ApplicationType.SERVICES_UPDATE,
        status=FacilityApplication.ApplicationStatus.APPROVED,
    ).order_by("-reviewed_at").first()
    return render(
        request,
        "registry/regulator_facility_detail.html",
        {
            "facility": facility,
            "staff": staff,
            "derived_status": derived_status,
            "logs": logs,
            "applications": applications_qs,
            "application_review_form": application_review_form,
            "review_application": review_application,
            "approved_services_update": approved_services_update,
            **dossier,
        },
    )


@role_required(User.Role.REGULATOR)
def compliance_analytics(request):
    run_compliance_scan()
    analytics = build_compliance_analytics()
    practitioner_rows = [
        {
            "label": status_label(row["status"]),
            "color": status_badge_color(row["status"]),
            "count": row["count"],
        }
        for row in analytics["practitioner_status"]
    ]
    facility_rows = [
        {
            "label": status_label(row["status"]),
            "color": status_badge_color(row["status"]),
            "count": row["count"],
        }
        for row in analytics["facility_status"]
    ]
    return render(
        request,
        "registry/compliance_analytics.html",
        {
            "analytics": analytics,
            "practitioner_rows": practitioner_rows,
            "facility_rows": facility_rows,
        },
    )


@role_required(User.Role.REGULATOR)
def audit_trail(request):
    logs = StatusChangeLog.objects.select_related("changed_by")[:100]
    checks = VerificationCheck.objects.select_related("performed_by")[:50]
    return render(request, "registry/audit.html", {"logs": logs, "checks": checks})


@role_required(User.Role.HOSPITAL_ADMIN)
def facility_renewal(request):
    facility = request.user.facility
    if not facility:
        messages.error(request, "No facility linked to your account.")
        return redirect("dashboard")

    # Enforce 1-month rule: cannot renew if more than 1 month remains before accreditation expiry
    today = timezone.now().date()
    if facility.accreditation_expiry > today and (facility.accreditation_expiry - today).days > 31:
        messages.warning(
            request,
            f"Renewal is not yet available. Your facility accreditation "
            f"({facility.registration_number}) expires on "
            f"{facility.accreditation_expiry.strftime('%d %b %Y')} — you may apply "
            f"for renewal only within 1 month of the expiry date.",
        )
        return redirect("dashboard")

    form = FacilityRenewalForm(request.POST if request.method == "POST" else None, instance=facility)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Facility profile updated. Await KMPDC accreditation renewal approval.")
        return redirect("dashboard")
    return render(request, "registry/renewal.html", {"form": form, "entity": facility, "entity_type": "facility"})


@role_required(User.Role.PRACTITIONER)
def practitioner_renewal(request):
    profile = request.user.practitioner_profile
    if not profile:
        messages.error(request, "No practitioner profile linked to your account.")
        return redirect("dashboard")

    today = timezone.now().date()
    has_rejected_renewal = PractitionerRenewalApplication.objects.filter(
        practitioner=profile,
        status=PractitionerRenewalApplication.ApplicationStatus.REJECTED,
    ).exists()
    has_active_renewal = PractitionerRenewalApplication.objects.filter(
        practitioner=profile,
        status__in=[
            PractitionerRenewalApplication.ApplicationStatus.PENDING,
        ],
    ).exists()
    if has_active_renewal:
        messages.error(
            request,
            "You already have an active licence renewal application. Please wait for regulator review or reapply only if your previous application was rejected.",
        )
        return redirect("dashboard")
    if not has_rejected_renewal:
        if profile.license_expiry > today and (profile.license_expiry - today).days > 31:
            messages.warning(
                request,
                f"Renewal is not yet available. Your licence "
                f"({profile.license_number}) expires on "
                f"{profile.license_expiry.strftime('%d %b %Y')} — you may apply "
                f"for renewal only within 1 month of the expiry date.",
            )
            return redirect("dashboard")

    duplicate_payment = PractitionerRenewalPayment.objects.filter(
        practitioner=profile,
        status__in=[
            PractitionerRenewalPayment.Status.PENDING,
            PractitionerRenewalPayment.Status.COMPLETED,
        ],
    ).exists()
    if duplicate_payment:
        messages.error(request, "You already have an active licence renewal payment. Complete or cancel it before starting a new one.")
        return redirect("dashboard")

    form = PractitionerLicenceRenewalForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        renewal_app = PractitionerRenewalApplication(
            practitioner=profile,
            current_employer=form.cleaned_data.get("current_employer", ""),
            work_contact_phone=form.cleaned_data.get("work_contact_phone", ""),
            work_email=form.cleaned_data.get("work_email", ""),
            has_practised_continuously=form.cleaned_data.get("has_practised_continuously", ""),
            practice_break_reason=form.cleaned_data.get("practice_break_reason", ""),
            has_malpractice_history=form.cleaned_data.get("has_malpractice_history", ""),
            malpractice_details=form.cleaned_data.get("malpractice_details", ""),
        )
        renewal_app.save()

        created_docs = []
        for field_name, doc_type in [
            ("indemnity_file", RegistryDocument.DocumentType.PROFESSIONAL_INDEMNITY),
            ("cpd_certificate_file", RegistryDocument.DocumentType.CPD_CERTIFICATE),
            ("licence_renewal_file", RegistryDocument.DocumentType.PRACTITIONER_LICENSE),
        ]:
            uploaded = form.cleaned_data.get(field_name)
            if uploaded:
                ref = f"{profile.license_number}-{field_name}-{timezone.now().strftime('%Y%m%d%H%M%S')}"
                expires_on = None
                if doc_type == RegistryDocument.DocumentType.PRACTITIONER_LICENSE:
                    expires_on = profile.license_expiry
                elif doc_type == RegistryDocument.DocumentType.PROFESSIONAL_INDEMNITY:
                    expires_on = profile.indemnity_expiry
                elif doc_type == RegistryDocument.DocumentType.CPD_CERTIFICATE:
                    expires_on = profile.license_expiry
                doc = RegistryDocument(
                    practitioner=profile,
                    document_type=doc_type,
                    title=f"{doc_type.replace('_', ' ').title()} — Renewal submission",
                    reference_number=ref,
                    review_status=RegistryDocument.ReviewStatus.PENDING,
                    expires_on=expires_on,
                )
                doc.file.save(uploaded.name, uploaded, save=True)
                created_docs.append(doc)
        if created_docs:
            messages.success(
                request,
                f"Renewal application submitted. {len(created_docs)} document(s) uploaded for review. "
                "A regulator will verify them and your CPD will be updated automatically upon verification.",
            )
        else:
            messages.warning(request, "Renewal form saved but no documents were uploaded. Please upload at least one supporting document.")

        amount = getattr(django_settings, "RENEWAL_FEE", 1000)
        payment = PractitionerRenewalPayment.objects.create(
            practitioner=profile,
            initiated_by=request.user,
            phone_number="",
            amount=amount,
            status=PractitionerRenewalPayment.Status.PENDING,
        )
        request.session["pending_practitioner_payment_id"] = payment.pk
        messages.success(request, "Renewal application saved. Complete the payment to finalise submission.")
        return redirect("practitioner_payment_step")

    previous_applications = PractitionerRenewalApplication.objects.filter(practitioner=profile)[:5]
    return render(
        request,
        "registry/renewal.html",
        {
            "entity": profile,
            "entity_type": "practitioner",
            "today": timezone.now().date(),
            "renewal_form": form,
            "previous_applications": previous_applications,
            "renewal_fee": getattr(django_settings, "RENEWAL_FEE", 1000),
        },
    )


@role_required(User.Role.PRACTITIONER)
def practitioner_payment_step(request):
    payment_id = request.session.get("pending_practitioner_payment_id") or request.GET.get("payment_id")
    if not payment_id:
        messages.error(request, "No pending payment found.")
        return redirect("practitioner_renewal")

    profile = request.user.practitioner_profile
    if not profile:
        messages.error(request, "No practitioner profile linked to your account.")
        return redirect("dashboard")

    payment = get_object_or_404(PractitionerRenewalPayment, pk=payment_id, practitioner=profile)

    if payment.status == PractitionerRenewalPayment.Status.COMPLETED:
        request.session.pop("pending_practitioner_payment_id", None)
        messages.success(request, "Payment confirmed. Your renewal application has been submitted.")
        return redirect("dashboard")

    if request.method == "POST":
        phone = request.POST.get("phone", "").strip()
        if not phone:
            messages.error(request, "Please provide a phone number to receive the payment prompt.")
            return redirect("practitioner_payment_step")
        try:
            callback_url = getattr(django_settings, "MPESA_CALLBACK_URL", "") or request.build_absolute_uri(reverse("mpesa_callback"))
            account_ref = f"REN-{profile.license_number}-{payment.pk}"
            resp = mpesa_client.stk_push(phone, payment.amount, account_ref, transaction_desc="Licence renewal", callback_url=callback_url)
            payment.merchant_request_id = resp.get("MerchantRequestID", "")
            payment.checkout_request_id = resp.get("CheckoutRequestID", "")
            payment.phone_number = phone
            payment.save(update_fields=["merchant_request_id", "checkout_request_id", "phone_number"])
            messages.info(request, "Payment prompt sent to your phone. Complete the payment on your device.")
        except Exception as e:
            messages.error(request, f"Failed to initiate payment: {e}")
        return redirect("practitioner_payment_step")

    return render(request, "registry/practitioner_payment_step.html", {"payment": payment})


@csrf_exempt
def mpesa_callback(request):
    """Endpoint to receive Daraja payment callbacks.

    Daraja posts JSON with the STK result. The function updates the related
    PractitionerRenewalPayment or FacilityRenewalPayment record using MerchantRequestID / CheckoutRequestID.
    """
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return HttpResponse(status=400)

    body = payload.get("Body") or {}
    stk = body.get("stkCallback") if isinstance(body, dict) else None
    if not stk:
        return HttpResponse(status=200)

    merchant_request_id = stk.get("MerchantRequestID")
    checkout_request_id = stk.get("CheckoutRequestID")
    result_code = stk.get("ResultCode")
    result_desc = stk.get("ResultDesc")

    payment = None

    payment_qs = PractitionerRenewalPayment.objects.all()
    if merchant_request_id:
        payment_qs = payment_qs.filter(merchant_request_id=merchant_request_id)
    elif checkout_request_id:
        payment_qs = payment_qs.filter(checkout_request_id=checkout_request_id)
    else:
        return HttpResponse(status=200)

    payment = payment_qs.first()
    if not payment:
        payment_qs = FacilityRenewalPayment.objects.all()
        if merchant_request_id:
            payment_qs = payment_qs.filter(merchant_request_id=merchant_request_id)
        elif checkout_request_id:
            payment_qs = payment_qs.filter(checkout_request_id=checkout_request_id)
        payment = payment_qs.first()

    if not payment:
        return HttpResponse(status=200)

    if result_code == 0:
        callback_metadata = stk.get("CallbackMetadata") or {}
        items = callback_metadata.get("Item") or []
        receipt = ""
        for item in items:
            name = item.get("Name")
            if name == "MpesaReceiptNumber":
                receipt = item.get("Value")
        payment.status = payment.Status.COMPLETED
        payment.mpesa_receipt_number = receipt or ""
        payment.save(update_fields=["status", "mpesa_receipt_number"])
    else:
        payment.status = payment.Status.FAILED
        payment.save(update_fields=["status"])

    return HttpResponse(status=200)


@role_required(User.Role.REGULATOR, User.Role.HOSPITAL_ADMIN, User.Role.PRACTITIONER, User.Role.SYSTEM_ADMIN)
def mark_alert_read(request, pk):
    alert = get_object_or_404(ComplianceAlert, pk=pk, recipient=request.user)
    alert.is_read = True
    alert.save(update_fields=["is_read"])
    return redirect("dashboard")


def submit_support_ticket(request):
    from sysadmin.forms import SubmitTicketForm
    from sysadmin.models import SupportTicket

    if not request.user.is_authenticated:
        return redirect("login")
    form = SubmitTicketForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        ticket = form.save(commit=False)
        ticket.submitted_by = request.user
        ticket.save()
        messages.success(request, f"Support ticket #{ticket.pk} submitted. An administrator will respond shortly.")
        return redirect("dashboard")
    return render(request, "sysadmin/submit_ticket.html", {"form": form})


def my_support_tickets(request):
    from sysadmin.models import SupportTicket

    if not request.user.is_authenticated:
        return redirect("login")
    tickets = SupportTicket.objects.filter(submitted_by=request.user)
    return render(request, "sysadmin/my_tickets.html", {"tickets": tickets})
