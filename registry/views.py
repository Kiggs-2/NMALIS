from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.conf import settings
from django.urls import reverse

from registry.forms import FacilityRenewalForm, PractitionerRenewalForm
from registry.models import (
    FacilityApplication,
    HealthcareFacility,
    MpesaStkTransaction,
    PractitionerProfile,
    PractitionerRenewalApplication,
    RegistryDocument,
    User,
)
from registry.mpesa.utils import stk_push


@login_required
def facility_renewal(request):
    facility = request.user.facility
    if not facility:
        messages.error(request, "No facility linked to your account.")
        return redirect("dashboard")

    step = request.GET.get("step", "form")
    renewal_fee = settings.MPESA_FACILITY_RENEWAL_FEE

    if step == "form":
        form = FacilityRenewalForm(request.POST or None, instance=facility)
        if request.method == "POST" and form.is_valid():
            form.save()
            # Create pending transaction
            pending_tx, created = MpesaStkTransaction.objects.get_or_create(
                user=request.user,
                renewal_type=MpesaStkTransaction.RenewalType.FACILITY,
                defaults={
                    "phone_number": "0700000000",
                    "amount": renewal_fee,
                    "account_reference": facility.registration_number,
                    "status": MpesaStkTransaction.Status.PENDING,
                },
            )
            messages.success(
                request,
                "Facility details saved. Complete M-Pesa payment to finalise your accreditation renewal.",
            )
            return redirect("renewal_payment", tx_id=pending_tx.pk)
        return render(request, "registry/facility_renewal_form.html", {"form": form, "step": "form"})

    # If step is payment, redirect to renewal_payment
    return redirect("renewal_payment", tx_id=request.GET.get("pending_tx_id", ""))


@login_required
def practitioner_renewal(request):
    profile = request.user.practitioner_profile
    if not profile:
        messages.error(request, "No practitioner profile linked to your account.")
        return redirect("dashboard")

    step = request.GET.get("step", "form")
    renewal_fee = settings.MPESA_PRACTITIONER_RENEWAL_FEE

    if step == "form":
        form = PractitionerRenewalForm(
            request.POST if request.method == "POST" else None,
            request.FILES if request.method == "POST" else None,
        )
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

            # Create pending transaction
            pending_tx, created = MpesaStkTransaction.objects.get_or_create(
                user=request.user,
                renewal_type=MpesaStkTransaction.RenewalType.PRACTITIONER,
                defaults={
                    "phone_number": "0700000000",
                    "amount": renewal_fee,
                    "account_reference": profile.license_number,
                    "status": MpesaStkTransaction.Status.PENDING,
                },
            )

            # Save documents
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
                        title=f"{doc_type.replace('_', ').title()} — Renewal submission",
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
            return redirect("renewal_payment", tx_id=pending_tx.pk)
        return render(request, "registry/practitioner_renewal_form.html", {"form": form, "step": "form"})

    # If step is payment, redirect to renewal_payment
    return redirect("renewal_payment", tx_id=request.GET.get("pending_tx_id", ""))


def renewal_payment(request, tx_id):
    transaction = get_object_or_404(MpesaStkTransaction, pk=tx_id)

    if request.method == "POST":
        phone_number = request.POST.get("phone_number")
        response = stk_push(
            user=request.user,
            phone_number=phone_number,
            amount=transaction.amount,
            account_reference=transaction.account_reference,
            renewal_type=transaction.renewal_type,
            practitioner=transaction.practitioner,
            facility=transaction.facility,
            practitioner_renewal=transaction.practitioner_renewal,
        )
        checkout_request_id = response.get("CheckoutRequestID")

        if checkout_request_id:
            transaction.checkout_request_id = checkout_request_id
            transaction.status = MpesaStkTransaction.Status.PENDING
            transaction.save()
            messages.success(request, "STK push sent! Please check your phone.")
        else:
            messages.error(request, "Failed to initiate M-Pesa push. Try again.")

    return render(request, "registry/renewal.html", {
        "step": "payment",
        "pending_tx": transaction,
    })


def cancel_stk_push(request, tx_id):
    transaction = get_object_or_404(MpesaStkTransaction, pk=tx_id)
    if transaction.status == MpesaStkTransaction.Status.PENDING:
        transaction.status = MpesaStkTransaction.Status.CANCELLED
        transaction.result_desc = "Cancelled by user."
        transaction.save(update_fields=["status", "result_desc", "updated_at"])
        messages.info(request, "Pending payment window has been cancelled.")
    return redirect("renewal_payment", tx_id=transaction.pk)


def resend_stk_push(request, tx_id):
    transaction = get_object_or_404(MpesaStkTransaction, pk=tx_id)
    phone_number = request.POST.get("phone_number") or transaction.phone_number
    response = stk_push(
        user=request.user,
        phone_number=phone_number,
        amount=transaction.amount,
        account_reference=transaction.account_reference,
        renewal_type=transaction.renewal_type,
        practitioner=transaction.practitioner,
        facility=transaction.facility,
        practitioner_renewal=transaction.practitioner_renewal,
    )
    checkout_request_id = response.get("CheckoutRequestID")

    if checkout_request_id:
        transaction.checkout_request_id = checkout_request_id
        transaction.status = MpesaStkTransaction.Status.PENDING
        transaction.save(update_fields=["checkout_request_id", "status", "updated_at"])
        messages.success(request, "A new STK push has been sent to your phone.")
    else:
        messages.error(request, "Failed to resend STK push. Please try again.")
    return redirect("renewal_payment", tx_id=transaction.pk)
