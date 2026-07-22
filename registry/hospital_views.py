import base64
import datetime

from django.conf import settings as django_settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .decorators import role_required
from .forms import FacilityLicenceApplicationForm, FacilityServicesUpdateForm
from .models import FacilityApplication, FacilityRenewalPayment, RegistryDocument, StaffAffiliation, User
from . import mpesa as mpesa_client


MAX_PENDING_APPLICATIONS_PER_FACILITY = 2
PENDING_PAYMENT_TIMEOUT_MINUTES = 30


def _facility_or_redirect(request):
    facility = request.user.facility
    if not facility:
        messages.error(request, "No facility linked to your account.")
        return None
    return facility


def request_email_placeholder(facility):
    admin = facility.admin_users.first()
    return admin.email if admin else ""


def _cancel_stale_pending_payments(facility):
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=PENDING_PAYMENT_TIMEOUT_MINUTES)
    stale_payments = FacilityRenewalPayment.objects.filter(
        facility=facility,
        status=FacilityRenewalPayment.Status.PENDING,
        created_at__lte=cutoff,
    )
    updated = stale_payments.update(status=FacilityRenewalPayment.Status.FAILED, updated_at=datetime.datetime.now(datetime.timezone.utc))
    return updated


def _create_registry_document_from_application(application, supporting_file):
    if not supporting_file:
        return None
    ref = f"APP-{application.facility.registration_number}-{application.pk}-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
    doc = RegistryDocument(
        facility=application.facility,
        document_type=RegistryDocument.DocumentType.FACILITY_ACCREDITATION,
        title=f"{application.get_application_type_display()} — supporting document",
        reference_number=ref,
        review_status=RegistryDocument.ReviewStatus.PENDING,
    )
    doc.file.save(supporting_file.name, supporting_file, save=True)
    return doc


@role_required(User.Role.HOSPITAL_ADMIN)
def hospital_apply_licence(request):
    facility = _facility_or_redirect(request)
    if not facility:
        return redirect("dashboard")

    today = datetime.date.today()
    expiry = facility.accreditation_expiry
    has_rejected_renewal = (
        expiry
        and FacilityApplication.objects.filter(
            facility=facility,
            application_type=FacilityApplication.ApplicationType.LICENCE_RENEWAL,
            status=FacilityApplication.ApplicationStatus.REJECTED,
        ).exists()
    )
    if expiry and not has_rejected_renewal:
        days_to_expiry = (expiry - today).days
        if days_to_expiry > 30:
            messages.error(
                request,
                f"Licence renewal is only available within 1 month of expiry. Your facility accreditation expires on {expiry.strftime('%d %B %Y')} ({days_to_expiry} days remaining).",
            )
            return redirect("hospital_facility_profile")

    pending_applications_count = FacilityApplication.objects.filter(
        facility=facility,
        status=FacilityApplication.ApplicationStatus.PENDING,
    ).count()
    if pending_applications_count >= MAX_PENDING_APPLICATIONS_PER_FACILITY:
        messages.error(
            request,
            f"You already have {pending_applications_count} pending application(s). Please wait for regulator review before submitting another.",
        )
        return redirect("hospital_facility_profile")

    duplicate_payment = FacilityRenewalPayment.objects.filter(
        facility=facility,
        payment_type=FacilityRenewalPayment.PaymentType.LICENCE_RENEWAL,
        status__in=[FacilityRenewalPayment.Status.PENDING, FacilityRenewalPayment.Status.COMPLETED],
    ).exists()
    if duplicate_payment:
        messages.error(request, "You already have an active licence renewal payment. Complete or cancel it before starting a new one.")
        return redirect("hospital_facility_profile")

    initial = {
        "facility_legal_name": facility.name,
        "registration_number": facility.registration_number,
        "county": facility.county,
        "physical_address": f"{facility.name}, {facility.county}",
        "services_requested": facility.services_offered,
        "accreditation_sought_until": facility.accreditation_expiry,
        "email": request_email_placeholder(facility),
    }

    if request.method == "POST":
        form = FacilityLicenceApplicationForm(request.POST, request.FILES)
        if form.is_valid():
            # Prevent duplicate application_type constraint error
            existing_app = FacilityApplication.objects.filter(
                facility=facility,
                application_type=FacilityApplication.ApplicationType.LICENCE_RENEWAL,
            ).first()

            if existing_app:
                app = form.save(commit=False)
                # Transfer valid form data to the existing record
                for field in form.cleaned_data:
                    setattr(existing_app, field, form.cleaned_data[field])
                existing_app.submitted_by = request.user
                existing_app.status = FacilityApplication.ApplicationStatus.PENDING
                existing_app.save()
                _create_registry_document_from_application(existing_app, form.cleaned_data.get("supporting_file"))
            else:
                app = form.save(commit=False)
                app.facility = facility
                app.application_type = FacilityApplication.ApplicationType.LICENCE_RENEWAL
                app.submitted_by = request.user
                app.save()
                _create_registry_document_from_application(app, form.cleaned_data.get("supporting_file"))

            payment = FacilityRenewalPayment.objects.create(
                facility=facility,
                initiated_by=request.user,
                phone_number="",
                amount=getattr(django_settings, "FACILITY_RENEWAL_FEE", 2000),
                payment_type=FacilityRenewalPayment.PaymentType.LICENCE_RENEWAL,
                status=FacilityRenewalPayment.Status.PENDING,
            )
            request.session["pending_facility_payment_id"] = payment.pk
            messages.success(request, "Application saved. Complete the payment to submit.")
            return redirect("facility_payment_step")
    else:
        form = FacilityLicenceApplicationForm(initial=initial)

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

    pending_applications_count = FacilityApplication.objects.filter(
        facility=facility,
        status=FacilityApplication.ApplicationStatus.PENDING,
    ).count()
    if pending_applications_count >= MAX_PENDING_APPLICATIONS_PER_FACILITY:
        messages.error(
            request,
            f"You already have {pending_applications_count} pending application(s). Please wait for regulator review before submitting another.",
        )
        return redirect("hospital_facility_profile")

    duplicate_payment = FacilityRenewalPayment.objects.filter(
        facility=facility,
        payment_type=FacilityRenewalPayment.PaymentType.SERVICES_UPDATE,
        status__in=[FacilityRenewalPayment.Status.PENDING, FacilityRenewalPayment.Status.COMPLETED],
    ).exists()
    if duplicate_payment:
        messages.error(request, "You already have an active services update payment. Complete or cancel it before starting a new one.")
        return redirect("hospital_facility_profile")

    initial = {
        "facility_legal_name": facility.name,
        "registration_number": facility.registration_number,
        "county": facility.county,
        "physical_address": f"{facility.name}, {facility.county}",
        "services_requested": facility.services_offered,
        "accreditation_sought_until": facility.accreditation_expiry,
        "email": request_email_placeholder(facility),
    }

    if request.method == "POST":
        form = FacilityServicesUpdateForm(request.POST, request.FILES)
        if form.is_valid():
            # Prevent duplicate application_type constraint error
            existing_app = FacilityApplication.objects.filter(
                facility=facility,
                application_type=FacilityApplication.ApplicationType.SERVICES_UPDATE,
            ).first()

            if existing_app:
                app = form.save(commit=False)
                # Transfer valid form data to the existing record
                for field in form.cleaned_data:
                    setattr(existing_app, field, form.cleaned_data[field])
                existing_app.submitted_by = request.user
                existing_app.status = FacilityApplication.ApplicationStatus.PENDING
                existing_app.save()
                _create_registry_document_from_application(existing_app, form.cleaned_data.get("supporting_file"))
            else:
                app = form.save(commit=False)
                app.facility = facility
                app.application_type = FacilityApplication.ApplicationType.SERVICES_UPDATE
                app.submitted_by = request.user
                app.save()
                _create_registry_document_from_application(app, form.cleaned_data.get("supporting_file"))

            payment = FacilityRenewalPayment.objects.create(
                facility=facility,
                initiated_by=request.user,
                phone_number="",
                amount=getattr(django_settings, "SERVICES_UPDATE_FEE", 1500),
                payment_type=FacilityRenewalPayment.PaymentType.SERVICES_UPDATE,
                status=FacilityRenewalPayment.Status.PENDING,
            )
            request.session["pending_facility_payment_id"] = payment.pk
            messages.success(request, "Application saved. Complete the payment to submit.")
            return redirect("facility_payment_step")
    else:
        form = FacilityServicesUpdateForm(initial=initial)

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
def facility_payment_step(request):
    payment_id = request.session.get("pending_facility_payment_id") or request.GET.get("payment_id")
    if not payment_id:
        messages.error(request, "No pending payment found.")
        return redirect("hospital_facility_profile")

    facility = request.user.facility
    if not facility:
        messages.error(request, "No facility linked to your account.")
        return redirect("dashboard")

    payment = get_object_or_404(FacilityRenewalPayment, pk=payment_id, facility=facility)

    if payment.status == FacilityRenewalPayment.Status.COMPLETED:
        request.session.pop("pending_facility_payment_id", None)
        messages.success(request, "Payment confirmed. Your application has been submitted.")
        return redirect("hospital_facility_profile")

    if request.method == "POST":
        phone = request.POST.get("phone", "").strip()
        if not phone:
            messages.error(request, "Please provide a phone number to receive the payment prompt.")
            return redirect("facility_payment_step")
        try:
            callback_url = getattr(django_settings, "MPESA_CALLBACK_URL", "") or request.build_absolute_uri(reverse("mpesa_callback"))
            account_ref = f"FAC-{facility.registration_number}-{payment.pk}"
            resp = mpesa_client.stk_push(phone, payment.amount, account_ref, transaction_desc=payment.get_payment_type_display(), callback_url=callback_url)
            payment.merchant_request_id = resp.get("MerchantRequestID", "")
            payment.checkout_request_id = resp.get("CheckoutRequestID", "")
            payment.phone_number = phone
            payment.save(update_fields=["merchant_request_id", "checkout_request_id", "phone_number"])
            messages.info(request, "Payment prompt sent to your phone. Complete the payment on your device.")
        except Exception as e:
            messages.error(request, f"Failed to initiate payment: {e}")
        return redirect("facility_payment_step")

    return render(request, "registry/facility_payment_step.html", {"payment": payment})


@role_required(User.Role.HOSPITAL_ADMIN)
def facility_check_payment(request, pk):
    facility = request.user.facility
    if not facility:
        messages.error(request, "No facility linked to your account.")
        return redirect("dashboard")

    payment = get_object_or_404(FacilityRenewalPayment, pk=pk, facility=facility)
    if payment.status == FacilityRenewalPayment.Status.COMPLETED:
        request.session.pop("pending_facility_payment_id", None)
        messages.success(request, "Payment is already confirmed.")
        return redirect("hospital_facility_profile")

    checkout_request_id = payment.checkout_request_id.strip()
    if not checkout_request_id:
        messages.error(request, "No payment request ID on file. Please start a new payment.")
        return redirect("facility_payment_step")

    shortcode = getattr(django_settings, "MPESA_SHORTCODE", "")
    passkey = getattr(django_settings, "MPESA_PASSKEY", "")
    if not shortcode or not passkey:
        messages.error(request, "M-Pesa credentials are not configured on the server.")
        return redirect("facility_payment_step")

    try:
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        password = base64.b64encode(f"{shortcode}{passkey}{timestamp}".encode()).decode()
        resp = mpesa_client.stk_push_query(shortcode, password, timestamp, checkout_request_id)
        result_code = resp.get("ResultCode")
        result_desc = resp.get("ResultDesc", "")
        if result_code == 0:
            payment.status = FacilityRenewalPayment.Status.COMPLETED
            payment.save(update_fields=["status"])
            request.session.pop("pending_facility_payment_id", None)
            messages.success(request, f"Payment confirmed. {result_desc}")
            return redirect("hospital_facility_profile")
        elif result_code == "2002" or result_code == 2002:
            messages.info(request, "Payment is still pending. Complete it on your phone and try again.")
        else:
            payment.status = FacilityRenewalPayment.Status.FAILED
            payment.save(update_fields=["status"])
            request.session.pop("pending_facility_payment_id", None)
            messages.error(request, f"Payment failed: {result_desc}")
            return redirect("hospital_facility_profile")
    except Exception as e:
        messages.error(request, f"Failed to check payment status: {e}")
    return redirect("facility_payment_step")


@role_required(User.Role.HOSPITAL_ADMIN)
def facility_cancel_payment(request, pk):
    facility = request.user.facility
    if not facility:
        messages.error(request, "No facility linked to your account.")
        return redirect("dashboard")

    payment = get_object_or_404(FacilityRenewalPayment, pk=pk, facility=facility)
    if payment.status == FacilityRenewalPayment.Status.PENDING:
        payment.status = FacilityRenewalPayment.Status.FAILED
        payment.save(update_fields=["status"])

    request.session.pop("pending_facility_payment_id", None)
    messages.info(request, "Payment cancelled.")
    return redirect("hospital_facility_profile")


@role_required(User.Role.HOSPITAL_ADMIN)
def facility_resend_payment(request, pk):
    facility = request.user.facility
    if not facility:
        messages.error(request, "No facility linked to your account.")
        return redirect("dashboard")

    payment = get_object_or_404(FacilityRenewalPayment, pk=pk, facility=facility)
    if payment.status != FacilityRenewalPayment.Status.PENDING:
        messages.error(request, "This payment is no longer pending.")
        return redirect("hospital_facility_profile")

    phone = payment.phone_number.strip()
    if not phone:
        messages.error(request, "No phone number on file. Please cancel and start again.")
        return redirect("facility_payment_step")

    try:
        callback_url = getattr(django_settings, "MPESA_CALLBACK_URL", "") or request.build_absolute_uri(reverse("mpesa_callback"))
        account_ref = f"FAC-{facility.registration_number}-{payment.pk}"
        resp = mpesa_client.stk_push(phone, payment.amount, account_ref, transaction_desc=payment.get_payment_type_display(), callback_url=callback_url)
        payment.merchant_request_id = resp.get("MerchantRequestID", "")
        payment.checkout_request_id = resp.get("CheckoutRequestID", "")
        payment.save(update_fields=["merchant_request_id", "checkout_request_id"])
        messages.info(request, "Payment prompt resent to your phone.")
    except Exception as e:
        messages.error(request, f"Failed to resend payment: {e}")
    return redirect("facility_payment_step")


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