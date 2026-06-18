from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from registry.models import (
    ComplianceAlert,
    FacilityApplication,
    HealthcareFacility,
    LicenseStatus,
    PractitionerProfile,
    RegistryDocument,
    StatusChangeLog,
    User,
)
from .forms import (
    ResetPasswordForm,
    SubmitTicketForm,
    SystemUserCreateForm,
    SystemUserEditForm,
    TicketResponseForm,
)
from .models import SupportTicket


def sysadmin_required(view_func):
    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if request.user.role != User.Role.SYSTEM_ADMIN:
            raise PermissionDenied("System administrator access only.")
        return view_func(request, *args, **kwargs)
    return _wrapped


@sysadmin_required
def dashboard(request):
    ctx = {
        "user_count": User.objects.count(),
        "active_users": User.objects.filter(is_active=True).count(),
        "practitioner_count": PractitionerProfile.objects.count(),
        "facility_count": HealthcareFacility.objects.count(),
        "open_tickets": SupportTicket.objects.filter(
            status__in=[SupportTicket.Status.OPEN, SupportTicket.Status.IN_PROGRESS]
        ).count(),
        "pending_documents": RegistryDocument.objects.filter(
            review_status=RegistryDocument.ReviewStatus.PENDING
        ).count(),
        "pending_applications": FacilityApplication.objects.filter(
            status=FacilityApplication.ApplicationStatus.PENDING
        ).count(),
        "recent_tickets": SupportTicket.objects.select_related("submitted_by", "assigned_to")[:10],
        "recent_logs": StatusChangeLog.objects.select_related("changed_by")[:10],
        "role_breakdown": list(
            User.objects.values("role").annotate(count=Count("id")).order_by("role")
        ),
    }
    return render(request, "sysadmin/dashboard.html", ctx)


@sysadmin_required
def user_list(request):
    q = request.GET.get("q", "").strip()
    role_filter = request.GET.get("role", "")
    qs = User.objects.select_related("facility", "practitioner_profile").order_by("username")
    if q:
        qs = qs.filter(Q(username__icontains=q) | Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))
    if role_filter:
        qs = qs.filter(role=role_filter)
    return render(request, "sysadmin/user_list.html", {
        "users": qs,
        "q": q,
        "role_filter": role_filter,
        "role_choices": User.Role.choices,
    })


@sysadmin_required
def user_create(request):
    form = SystemUserCreateForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        messages.success(request, f"User '{user.username}' created successfully.")
        return redirect("sysadmin_user_detail", pk=user.pk)
    return render(request, "sysadmin/user_form.html", {"form": form, "form_title": "Create new user"})


@sysadmin_required
def user_detail(request, pk):
    target_user = get_object_or_404(User.objects.select_related("facility", "practitioner_profile"), pk=pk)
    tickets = target_user.support_tickets.all()[:10]
    alerts = ComplianceAlert.objects.filter(recipient=target_user).order_by("-created_at")[:10]
    return render(request, "sysadmin/user_detail.html", {
        "target_user": target_user,
        "tickets": tickets,
        "alerts": alerts,
    })


@sysadmin_required
def user_edit(request, pk):
    target_user = get_object_or_404(User, pk=pk)
    form = SystemUserEditForm(request.POST if request.method == "POST" else None, instance=target_user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"User '{target_user.username}' updated.")
        return redirect("sysadmin_user_detail", pk=pk)
    return render(request, "sysadmin/user_form.html", {
        "form": form,
        "form_title": f"Edit user: {target_user.username}",
        "target_user": target_user,
    })


@sysadmin_required
def user_reset_password(request, pk):
    target_user = get_object_or_404(User, pk=pk)
    form = ResetPasswordForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        target_user.set_password(form.cleaned_data["new_password"])
        target_user.save(update_fields=["password"])
        messages.success(request, f"Password reset for '{target_user.username}'.")
        return redirect("sysadmin_user_detail", pk=pk)
    return render(request, "sysadmin/reset_password.html", {
        "form": form,
        "target_user": target_user,
    })


@sysadmin_required
def ticket_list(request):
    status_filter = request.GET.get("status", "")
    qs = SupportTicket.objects.select_related("submitted_by", "assigned_to")
    if status_filter:
        qs = qs.filter(status=status_filter)
    return render(request, "sysadmin/ticket_list.html", {
        "tickets": qs,
        "status_filter": status_filter,
        "status_choices": SupportTicket.Status.choices,
    })


@sysadmin_required
def ticket_detail(request, pk):
    ticket = get_object_or_404(SupportTicket.objects.select_related("submitted_by", "assigned_to"), pk=pk)
    form = TicketResponseForm(initial={"status": ticket.status, "admin_notes": ticket.admin_notes})
    if request.method == "POST":
        form = TicketResponseForm(request.POST)
        if form.is_valid():
            ticket.status = form.cleaned_data["status"]
            ticket.admin_notes = form.cleaned_data["admin_notes"]
            ticket.assigned_to = request.user
            ticket.save(update_fields=["status", "admin_notes", "assigned_to", "updated_at"])
            messages.success(request, f"Ticket #{ticket.pk} updated.")
            return redirect("sysadmin_ticket_detail", pk=pk)
    return render(request, "sysadmin/ticket_detail.html", {"ticket": ticket, "form": form})


@sysadmin_required
def system_audit(request):
    logs = StatusChangeLog.objects.select_related("changed_by")[:200]
    return render(request, "sysadmin/audit.html", {"logs": logs})


def submit_ticket(request):
    """Any logged-in user can submit a support ticket."""
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


def my_tickets(request):
    """Any logged-in user can see their own tickets."""
    if not request.user.is_authenticated:
        return redirect("login")
    tickets = SupportTicket.objects.filter(submitted_by=request.user)
    return render(request, "sysadmin/my_tickets.html", {"tickets": tickets})
