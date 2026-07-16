import urllib.parse
import mimetypes

from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.views import LoginView
from django.db.models import Count, Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView

from .decorators import role_required
from .analytics import build_compliance_analytics
from .application_services import approve_facility_application, reject_facility_application
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
    HealthcareFacility,
    LicenseStatus,
    MpesaStkTransaction,
    PractitionerProfile,
    PractitionerRenewalApplication,
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
from .mpesa.utils import get_user_pending_transaction, stk_push


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
    pending_applications = FacilityApplication.objects.filter(
        status=FacilityApplication.ApplicationStatus.PENDING
    ).count()
    ctx = {
        "practitioner_count": PractitionerProfile.objects.count(),
        "facility_count": HealthcareFacility.objects.count(),
        "pending_documents": pending_documents,
        "pending_applications": pending_applications,
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
    system_admin_email = getattr(
        django_settings,
        "SYSTEM_ADMIN_EMAIL",
        "nmalis.admin@kabarak.edu.ke",
    )

    subject = f"National Medical Accreditation and Licensing Information System: regulator account correction ({user.username})"
    facility = user.facility
    facility_text = (
        f"{facility.name} ({facility.registration_number})" if facility else "Not linked"
    )
    body = (
        "Hello System Administrator,\n\n"
        "I am requesting a correction to my regulator account details.\n\n"
        f"Requested by: {user.get_full_name() or user.username}\n"
        f"Username: {user.username}\n"
        f"Current email: {user.email or '—'}\n"
        f"Linked facility: {facility_text}\n\n"
        "Please update my details after verification.\n\n"
        "Correction request:\n"
        "- (Write the exact correction here)\n\n"
        f"Thank you,\n{user.get_full_name() or user.username}\n"
    )

    mailto_href = (
        f"mailto:{system_admin_email}"
        f"?subject={urllib.parse.quote(subject)}"
        f"&body={urllib.parse.quote(body)}"
    )

    return render(
        request,
        "registry/regulator_account.html",
        {
            "user": user,
            "facility": user.facility,
            "system_admin_email": system_admin_email,
            "mailto_href": mailto_href,
        },
    )


def _account_mailto(user, role_label: str):
    system_admin_email = getattr(
        django_settings,
        "SYSTEM_ADMIN_EMAIL",
        "nmalis.admin@kabarak.edu.ke",
    )
    subject = (
        "National Medical Accreditation and Licensing Information System: "
        f"{role_label} account correction ({user.username})"
    )
    body = (
        "Hello System Administrator,\n\n"
        f"I am requesting a correction to my {role_label} account details.\n\n"
        f"Username: {user.username}\n"
        f"Current email: {user.email or '—'}\n\n"
        "Correction request:\n- (Write the exact correction here)\n\n"
        f"Thank you,\n{user.get_full_name() or user.username}\n"
    )
    return system_admin_email, (
        f"mailto:{system_admin_email}"
        f"?subject={urllib.parse.quote(subject)}"
        f"&body={urllib.parse.quote(body)}"
    )


@role_required(User.Role.PRACTITIONER)
def practitioner_account(request):
    user = request.user
    profile = user.practitioner_profile
    system_admin_email, mailto_href = _account_mailto(user, "practitioner")
    return render(
        request,
        "registry/practitioner_account.html",
        {"user": user, "profile": profile, "system_admin_email": system_admin_email, "mailto_href": mailto_href},
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
    system_admin_email, mailto_href = _account_mailto(user, "hospital administrator")
    return render(
        request,
        "registry/hospital_account.html",
        {
            "user": user,
            "facility": facility,
            "personal_physician": personal_physician,
            "pending_apps": pending_apps,
            "system_admin_email": system_admin_email,
            "mailto_href": mailto_href,
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
    return None, dossier


@role_required(User.Role.REGULATOR)
def regulator_practitioner_detail(request, pk):
    refresh_subject_statuses(triggered_by=request.user)
    practitioner = get_object_or_404(PractitionerProfile, pk=pk)
    documents_qs = practitioner.documents.select_related("reviewed_by").order_by("document_type", "-submitted_at")

    # Derive the logical status from documents, expiry, and CPD
    derived_status = derive_practitioner_status(practitioner)
    dossier = build_dossier_context(documents_qs)

    if request.method == "POST":
        response, dossier_override = _handle_dossier_review(request, documents_qs)
        if response is not None:
            return response
        dossier = dossier_override
        # Refresh derivation after document review
        derived_status = derive_practitioner_status(practitioner)

    logs = StatusChangeLog.objects.filter(entity_type="practitioner", entity_id=practitioner.pk)[:10]
    return render(
        request,
        "registry/regulator_practitioner_detail.html",
        {
            "practitioner": practitioner,
            "derived_status": derived_status,
            "logs": logs,
            **dossier,
        },
    )


@role_required(User.Role.REGULATOR)
def regulator_facility_detail(request, pk):
    refresh_subject_statuses(triggered_by=request.user)
    facility = get_object_or_404(HealthcareFacility, pk=pk)
    documents_qs = facility.documents.select_related("reviewed_by").order_by("document_type", "-submitted_at")

    # Derive the logical status from documents and expiry
    derived_status = derive_facility_status(facility)
    dossier = build_dossier_context(documents_qs)

    if request.method == "POST":
        response, dossier_override = _handle_dossier_review(request, documents_qs)
        if response is not None:
            return response
        dossier = dossier_override
        derived_status = derive_facility_status(facility)

    staff = StaffAffiliation.objects.filter(facility=facility, is_active=True).select_related("practitioner")
    logs = StatusChangeLog.objects.filter(entity_type="facility", entity_id=facility.pk)[:10]
    return render(
        request,
        "registry/regulator_facility_detail.html",
        {
            "facility": facility,
            "staff": staff,
            "derived_status": derived_status,
            "logs": logs,
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
def regulator_applications(request):
    status_filter = request.GET.get("status", FacilityApplication.ApplicationStatus.PENDING)
    qs = FacilityApplication.objects.select_related("facility", "submitted_by").order_by("-created_at")
    if status_filter:
        qs = qs.filter(status=status_filter)
    return render(
        request,
        "registry/regulator_applications.html",
        {
            "applications": qs[:100],
            "status_filter": status_filter,
            "status_choices": FacilityApplication.ApplicationStatus.choices,
        },
    )


@role_required(User.Role.REGULATOR)
def regulator_application_review(request, pk):
    application = get_object_or_404(
        FacilityApplication.objects.select_related("facility", "submitted_by"),
        pk=pk,
    )
    is_locked = application.status != FacilityApplication.ApplicationStatus.PENDING
    form = None if is_locked else FacilityApplicationReviewForm(request.POST if request.method == "POST" else None)
    if not is_locked and request.method == "POST" and form.is_valid():
        decision = form.cleaned_data["decision"]
        notes = form.cleaned_data.get("review_notes", "")
        if decision == "approved":
            approve_facility_application(application, request.user)
            messages.success(request, "Application approved. Facility records updated.")
        else:
            reject_facility_application(application, request.user, notes)
            messages.warning(request, "Application rejected.")
        return redirect("regulator_applications")

    return render(
        request,
        "registry/regulator_application_review.html",
        {"application": application, "form": form, "is_locked": is_locked},
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

    step = request.GET.get("step", "form")
    pending_tx = get_user_pending_transaction(request.user)
    renewal_fee = django_settings.MPESA_FACILITY_RENEWAL_FEE

    if step == "payment":
        if request.method == "POST" and request.POST.get("action") == "initiate_payment":
            phone = request.POST.get("mpesa_phone", "").strip()
            try:
                stk_push(
                    user=request.user,
                    phone_number=phone,
                    amount=renewal_fee,
                    account_reference=facility.registration_number,
                    renewal_type=MpesaStkTransaction.RenewalType.FACILITY,
                    facility=facility,
                )
                messages.success(
                    request,
                    "M-Pesa STK push sent. Check your phone and enter your PIN to complete payment.",
                )
            except (ValueError, RuntimeError) as exc:
                messages.error(request, str(exc))
            return redirect(f"{reverse('facility_renewal')}?step=payment")

        return render(
            request,
            "registry/renewal.html",
            {
                "entity": facility,
                "entity_type": "facility",
                "step": "payment",
                "renewal_fee": renewal_fee,
                "pending_tx": get_user_pending_transaction(request.user),
            },
        )

    form = FacilityRenewalForm(request.POST if request.method == "POST" else None, instance=facility)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(
            request,
            "Facility details saved. Complete M-Pesa payment to finalise your accreditation renewal.",
        )
        return redirect(f"{reverse('facility_renewal')}?step=payment")
    return render(
        request,
        "registry/renewal.html",
        {
            "form": form,
            "entity": facility,
            "entity_type": "facility",
            "step": "form",
            "pending_tx": pending_tx,
            "renewal_fee": renewal_fee,
        },
    )


@role_required(User.Role.PRACTITIONER)
def practitioner_renewal(request):
    profile = request.user.practitioner_profile
    if not profile:
        messages.error(request, "No practitioner profile linked to your account.")
        return redirect("dashboard")

    # Enforce 1-month rule: cannot renew if more than 1 month remains before expiry
    today = timezone.now().date()
    if profile.license_expiry > today and (profile.license_expiry - today).days > 31:
        messages.warning(
            request,
            f"Renewal is not yet available. Your licence "
            f"({profile.license_number}) expires on "
            f"{profile.license_expiry.strftime('%d %b %Y')} — you may apply "
            f"for renewal only within 1 month of the expiry date.",
        )
        return redirect("dashboard")

    step = request.GET.get("step", "form")
    renewal_id = request.GET.get("renewal_id")
    pending_tx = get_user_pending_transaction(request.user)
    renewal_fee = django_settings.MPESA_PRACTITIONER_RENEWAL_FEE

    if step == "payment":
        renewal_app = None
        if renewal_id:
            renewal_app = PractitionerRenewalApplication.objects.filter(
                pk=renewal_id,
                practitioner=profile,
            ).first()
        if not renewal_app:
            renewal_app = profile.renewal_applications.order_by("-submitted_at").first()
        if not renewal_app:
            messages.warning(request, "Submit your renewal application before proceeding to payment.")
            return redirect("practitioner_renewal")

        if request.method == "POST" and request.POST.get("action") == "initiate_payment":
            phone = request.POST.get("mpesa_phone", "").strip()
            try:
                stk_push(
                    user=request.user,
                    phone_number=phone,
                    amount=renewal_fee,
                    account_reference=profile.license_number,
                    renewal_type=MpesaStkTransaction.RenewalType.PRACTITIONER,
                    practitioner=profile,
                    practitioner_renewal=renewal_app,
                )
                messages.success(
                    request,
                    "M-Pesa STK push sent. Check your phone and enter your PIN to complete payment.",
                )
            except (ValueError, RuntimeError) as exc:
                messages.error(request, str(exc))
            return redirect(f"practitioner_renewal?step=payment&renewal_id={renewal_app.pk}")

        return render(
            request,
            "registry/renewal.html",
            {
                "entity": profile,
                "entity_type": "practitioner",
                "step": "payment",
                "renewal_app": renewal_app,
                "renewal_fee": renewal_fee,
                "pending_tx": get_user_pending_transaction(request.user),
            },
        )

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
                doc = RegistryDocument(
                    practitioner=profile,
                    document_type=doc_type,
                    title=f"{doc_type.replace('_', ' ').title()} — Renewal submission",
                    reference_number=ref,
                    review_status=RegistryDocument.ReviewStatus.PENDING,
                )
                doc.file.save(uploaded.name, uploaded, save=True)
                created_docs.append(doc)
        if created_docs:
            messages.success(
                request,
                f"Renewal application submitted ({len(created_docs)} document(s) uploaded). "
                "Proceed to M-Pesa payment to complete your renewal.",
            )
        else:
            messages.warning(
                request,
                "Renewal form saved but no documents were uploaded. "
                "Proceed to payment, or return to upload supporting documents.",
            )
        return redirect(f"practitioner_renewal?step=payment&renewal_id={renewal_app.pk}")

    previous_applications = PractitionerRenewalApplication.objects.filter(
        practitioner=profile
    )[:5]
    return render(
        request,
        "registry/renewal.html",
        {
            "entity": profile,
            "entity_type": "practitioner",
            "today": timezone.now().date(),
            "renewal_form": form,
            "previous_applications": previous_applications,
            "step": "form",
            "pending_tx": pending_tx,
            "renewal_fee": renewal_fee,
        },
    )


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
