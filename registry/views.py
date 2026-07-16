from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from registry.models import MpesaStkTransaction  # Adjust based on your transaction model name
from registry.mpesa.utils import stk_push  # Adjust path to your STK helper

def renewal_flow(request):
    # Step 1: Handle form details first
    # After forms are successfully saved/validated:
    # Create a pending transaction record
    # Redirect to the payment step: return redirect('renewal_payment', tx_id=transaction.id)
    pass  # Replace with actual form handling logic

def renewal_payment(request, tx_id):
    transaction = get_object_or_404(MpesaStkTransaction, pk=tx_id)
    
    # If the user submits the payment form to initiate STK push
    if request.method == 'POST':
        phone_number = request.POST.get('phone_number')
        # Fire STK push
        response = stk_push(
            user=request.user,
            phone_number=phone_number,
            amount=transaction.amount,
            account_reference=transaction.account_reference,
            renewal_type=transaction.renewal_type,
            practitioner=transaction.practitioner,
            facility=transaction.facility,
            practitioner_renewal=transaction.practitioner_renewal
        )
        checkout_request_id = response.get('CheckoutRequestID')
        
        if checkout_request_id:
            transaction.checkout_request_id = checkout_request_id
            transaction.status = MpesaStkTransaction.Status.PENDING
            transaction.save()
            messages.success(request, "STK push sent! Please check your phone.")
        else:
            messages.error(request, "Failed to initiate M-Pesa push. Try again.")
            
    return render(request, 'registry/renewal.html', {
        'step': 'payment',
        'pending_tx': transaction,
    })

def cancel_stk_push(request, tx_id):
    transaction = get_object_or_404(MpesaStkTransaction, pk=tx_id)
    if transaction.status == MpesaStkTransaction.Status.PENDING:
        transaction.status = MpesaStkTransaction.Status.CANCELLED
        transaction.result_desc = "Cancelled by user."
        transaction.save(update_fields=["status", "result_desc", "updated_at"])
        messages.info(request, "Pending payment window has been cancelled.")
    return redirect('renewal_payment', tx_id=transaction.pk)

def resend_stk_push(request, tx_id):
    transaction = get_object_or_404(MpesaStkTransaction, pk=tx_id)
    # Re-fire STK push helper
    phone_number = request.POST.get('phone_number') or transaction.phone_number
    response = stk_push(
        user=request.user,
        phone_number=phone_number,
        amount=transaction.amount,
        account_reference=transaction.account_reference,
        renewal_type=transaction.renewal_type,
        practitioner=transaction.practitioner,
        facility=transaction.facility,
        practitioner_renewal=transaction.practitioner_renewal
    )
    checkout_request_id = response.get('CheckoutRequestID')
    
    if checkout_request_id:
        transaction.checkout_request_id = checkout_request_id
        transaction.status = MpesaStkTransaction.Status.PENDING
        transaction.save(update_fields=["checkout_request_id", "status", "updated_at"])
        messages.success(request, "A new STK push has been sent to your phone.")
    else:
        messages.error(request, "Failed to resend STK push. Please try again.")
    return redirect('renewal_payment', tx_id=transaction.pk)
