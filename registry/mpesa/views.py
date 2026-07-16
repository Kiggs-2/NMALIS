import json
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from registry.models import MpesaStkTransaction

from .utils import activate_renewal_membership, stk_push

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def mpesa_callback(request):
    """Safaricom STK Push callback — parse ResultCode and activate renewal on success."""
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.warning("M-Pesa callback received invalid JSON.")
        return JsonResponse({"ResultCode": 1, "ResultDesc": "Invalid payload"})

    stk_callback = payload.get("Body", {}).get("stkCallback", {})
    checkout_request_id = stk_callback.get("CheckoutRequestID", "")
    result_code = stk_callback.get("ResultCode")
    result_desc = stk_callback.get("ResultDesc", "")

    if not checkout_request_id:
        return JsonResponse({"ResultCode": 1, "ResultDesc": "Missing CheckoutRequestID"})

    tx = MpesaStkTransaction.objects.filter(checkout_request_id=checkout_request_id).first()
    if not tx:
        logger.warning("M-Pesa callback for unknown CheckoutRequestID: %s", checkout_request_id)
        return JsonResponse({"ResultCode": 0, "ResultDesc": "Accepted"})

    if tx.status == MpesaStkTransaction.Status.COMPLETED:
        return JsonResponse({"ResultCode": 0, "ResultDesc": "Already processed"})

    tx.result_code = result_code
    tx.result_desc = result_desc

    if result_code == 0:
        metadata = stk_callback.get("CallbackMetadata", {}).get("Item", [])
        for item in metadata:
            if item.get("Name") == "MpesaReceiptNumber":
                tx.mpesa_receipt_number = str(item.get("Value", ""))
        tx.status = MpesaStkTransaction.Status.COMPLETED
        tx.save()
        activate_renewal_membership(tx)
        logger.info("M-Pesa payment completed for transaction %s", tx.pk)
    else:
        tx.status = MpesaStkTransaction.Status.FAILED
        tx.save()
        logger.info("M-Pesa payment failed for transaction %s: %s", tx.pk, result_desc)

    return JsonResponse({"ResultCode": 0, "ResultDesc": "Accepted"})


@login_required
@require_POST
def cancel_pending(request, pk):
    """Cancel a pending STK push and clear the waiting state."""
    tx = get_object_or_404(
        MpesaStkTransaction,
        pk=pk,
        user=request.user,
        status=MpesaStkTransaction.Status.PENDING,
    )
    tx.status = MpesaStkTransaction.Status.CANCELLED
    tx.result_desc = "Cancelled by user."
    tx.save(update_fields=["status", "result_desc", "updated_at"])

    redirect_url = _renewal_redirect_for(tx)
    messages.info(request, "Pending M-Pesa payment cancelled. You can initiate a new payment when ready.")
    return redirect(redirect_url)


@login_required
@require_POST
def resend_pending(request, pk):
    """Re-fire the STK push for a pending, cancelled, or failed transaction."""
    tx = get_object_or_404(
        MpesaStkTransaction,
        pk=pk,
        user=request.user,
    )
    if tx.status not in (
        MpesaStkTransaction.Status.PENDING,
        MpesaStkTransaction.Status.CANCELLED,
        MpesaStkTransaction.Status.FAILED,
    ):
        messages.warning(request, "This payment cannot be resent.")
        return redirect(_renewal_redirect_for(tx))

    try:
        stk_push(
            user=request.user,
            phone_number=tx.phone_number,
            amount=tx.amount,
            account_reference=tx.account_reference,
            renewal_type=tx.renewal_type,
            practitioner=tx.practitioner,
            facility=tx.facility,
            practitioner_renewal=tx.practitioner_renewal,
        )
        messages.success(request, "M-Pesa STK push resent. Check your phone to enter your PIN.")
    except (ValueError, RuntimeError) as exc:
        messages.error(request, str(exc))

    return redirect(_renewal_redirect_for(tx))


def _renewal_redirect_for(tx: MpesaStkTransaction) -> str:
    from django.urls import reverse

    if tx.renewal_type == MpesaStkTransaction.RenewalType.PRACTITIONER:
        url = reverse("practitioner_renewal")
        if tx.practitioner_renewal_id:
            return f"{url}?step=payment&renewal_id={tx.practitioner_renewal_id}"
        return f"{url}?step=payment"
    return f"{reverse('facility_renewal')}?step=payment"
