from datetime import timedelta

from dateutil.relativedelta import relativedelta
from django.conf import settings as django_settings
from django.utils import timezone

from .models import (
    ComplianceAlert,
    HealthcareFacility,
    LicenseStatus,
    PractitionerProfile,
    RegistryDocument,
    StatusChangeLog,
    User,
    VerificationCheck,
)


def log_status_change(
    entity,
    old_status: str,
    new_status: str,
    user,
    reason: str = "",
    *,
    accountability_confirmed: bool = False,
    accountability_statement: str = "",
):
    entity_type = "practitioner" if isinstance(entity, PractitionerProfile) else "facility"
    label = str(entity)
    StatusChangeLog.objects.create(
        entity_type=entity_type,
        entity_id=entity.pk,
        entity_label=label,
        old_status=old_status or "",
        new_status=new_status,
        reason=reason,
        accountability_confirmed=accountability_confirmed,
        accountability_statement=accountability_statement,
        changed_by=user,
    )


def derive_practitioner_status(practitioner: PractitionerProfile) -> str:
    """Automatically derive status from documents, dates, and CPD."""
    today = timezone.now().date()

    # Expiry check — hard failure
    if practitioner.license_expiry < today or practitioner.indemnity_expiry < today:
        return LicenseStatus.EXPIRED

    # Any rejected document → suspension
    if practitioner.documents.filter(review_status=RegistryDocument.ReviewStatus.REJECTED).exists():
        return LicenseStatus.SUSPENDED

    # CPD below threshold → pending renewal
    if not practitioner.cpd_meets_threshold:
        return LicenseStatus.PENDING_RENEWAL

    # Has documents — all must be verified for active status
    has_documents = practitioner.documents.exists()
    if has_documents:
        has_pending = practitioner.documents.exclude(
            review_status=RegistryDocument.ReviewStatus.VERIFIED
        ).exists()
        if not has_pending:
            return LicenseStatus.ACTIVE
        return LicenseStatus.PENDING_RENEWAL  # still has un-reviewed docs

    # No documents on file — cannot be active
    return LicenseStatus.PENDING_RENEWAL


def derive_facility_status(facility: HealthcareFacility) -> str:
    """Automatically derive facility status from documents and expiry."""
    today = timezone.now().date()
    if facility.accreditation_expiry < today:
        return LicenseStatus.EXPIRED
    if facility.documents.filter(review_status=RegistryDocument.ReviewStatus.REJECTED).exists():
        return LicenseStatus.SUSPENDED
    has_documents = facility.documents.exists()
    if has_documents:
        has_pending = facility.documents.exclude(
            review_status=RegistryDocument.ReviewStatus.VERIFIED
        ).exists()
        if not has_pending:
            return LicenseStatus.ACTIVE
        return LicenseStatus.PENDING_RENEWAL
    return LicenseStatus.PENDING_RENEWAL


def set_practitioner_status(
    practitioner: PractitionerProfile,
    new_status: str,
    user,
    reason: str = "",
    *,
    accountability_confirmed: bool = False,
    accountability_statement: str = "",
):
    old = practitioner.status
    if old == new_status:
        return
    practitioner.status = new_status
    practitioner.save(update_fields=["status", "updated_at"])
    log_status_change(
        practitioner,
        old,
        new_status,
        user,
        reason,
        accountability_confirmed=accountability_confirmed,
        accountability_statement=accountability_statement,
    )
    _notify_practitioner_status_change(practitioner, new_status, old)
    propagate_practitioner_suspension(practitioner, new_status, user)


def set_facility_status(
    facility: HealthcareFacility,
    new_status: str,
    user,
    reason: str = "",
    *,
    accountability_confirmed: bool = False,
    accountability_statement: str = "",
):
    old = facility.status
    if old == new_status:
        return
    facility.status = new_status
    facility.save(update_fields=["status", "updated_at"])
    log_status_change(
        facility,
        old,
        new_status,
        user,
        reason,
        accountability_confirmed=accountability_confirmed,
        accountability_statement=accountability_statement,
    )
    _notify_facility_status_change(facility, new_status, old)
    propagate_facility_suspension(facility, new_status, user)


def propagate_practitioner_suspension(practitioner: PractitionerProfile, new_status: str, regulator_user):
    if new_status not in (LicenseStatus.SUSPENDED, LicenseStatus.REVOKED):
        return
    for aff in practitioner.affiliations.filter(is_active=True).select_related("facility"):
        admins = User.objects.filter(
            role=User.Role.HOSPITAL_ADMIN,
            facility=aff.facility,
        )
        for admin in admins:
            ComplianceAlert.objects.create(
                alert_type=ComplianceAlert.AlertType.STATUS_CHANGED,
                recipient=admin,
                title=f"Staff status change: {practitioner.full_name}",
                message=(
                    f"KMPDC has set {practitioner.full_name} ({practitioner.license_number}) "
                    f"to {practitioner.get_status_display()}. Review payroll and clinical duties immediately."
                ),
                related_practitioner=practitioner,
                related_facility=aff.facility,
            )


def propagate_facility_suspension(facility: HealthcareFacility, new_status: str, regulator_user):
    if new_status not in (LicenseStatus.SUSPENDED, LicenseStatus.REVOKED):
        return
    for aff in facility.staff_affiliations.filter(is_active=True).select_related("practitioner"):
        try:
            user = aff.practitioner.user_account
        except User.DoesNotExist:
            continue
        ComplianceAlert.objects.create(
            alert_type=ComplianceAlert.AlertType.STATUS_CHANGED,
            recipient=user,
            title=f"Facility status change: {facility.name}",
            message=(
                f"{facility.name} ({facility.registration_number}) is now "
                f"{facility.get_status_display()}. Verify your employment arrangements."
            ),
            related_facility=facility,
            related_practitioner=aff.practitioner,
        )


def refresh_subject_statuses(triggered_by=None):
    for practitioner in PractitionerProfile.objects.all():
        desired = derive_practitioner_status(practitioner)
        if desired != practitioner.status:
            set_practitioner_status(
                practitioner,
                desired,
                triggered_by,
                reason="Automatic status recalculation from document and expiry checks.",
            )
    for facility in HealthcareFacility.objects.all():
        desired = derive_facility_status(facility)
        if desired != facility.status:
            set_facility_status(
                facility,
                desired,
                triggered_by,
                reason="Automatic status recalculation from document and expiry checks.",
            )


def _notify_practitioner_status_change(practitioner: PractitionerProfile, new_status: str, old_status: str):
    try:
        recipient = practitioner.user_account
    except User.DoesNotExist:
        return
    ComplianceAlert.objects.create(
        alert_type=ComplianceAlert.AlertType.STATUS_CHANGED,
        recipient=recipient,
        title=f"Licence status updated: {practitioner.full_name}",
        message=(
            f"Your professional standing changed from {dict(LicenseStatus.choices).get(old_status, old_status)} "
            f"to {practitioner.get_status_display()}."
        ),
        related_practitioner=practitioner,
    )


def _notify_facility_status_change(facility: HealthcareFacility, new_status: str, old_status: str):
    admins = User.objects.filter(role=User.Role.HOSPITAL_ADMIN, facility=facility)
    old_label = dict(LicenseStatus.choices).get(old_status, old_status)
    for admin in admins:
        ComplianceAlert.objects.create(
            alert_type=ComplianceAlert.AlertType.STATUS_CHANGED,
            recipient=admin,
            title=f"Facility status updated: {facility.name}",
            message=(
                f"Facility accreditation status changed from {old_label} "
                f"to {facility.get_status_display()}."
            ),
            related_facility=facility,
        )


def apply_document_review_outcome(document: RegistryDocument, reviewed_by):
    """
    Apply linked entity outcomes after a regulator verifies/rejects a document.
    - Rejected document => suspend linked practitioner/facility.
    - Verified document => notify and issue downloadable certificate when active.
    """
    from .certificate_services import issue_facility_certificate, issue_practitioner_certificate

    refresh_subject_statuses(triggered_by=reviewed_by)

    if document.review_status == RegistryDocument.ReviewStatus.VERIFIED:
        if document.practitioner_id:
            practitioner = document.practitioner
            today = timezone.now().date()
            if document.document_type == RegistryDocument.DocumentType.PRACTITIONER_LICENSE:
                if practitioner.license_expiry < today:
                    practitioner.license_expiry = today
                practitioner.license_expiry = practitioner.license_expiry + relativedelta(years=1)
                practitioner.save(update_fields=["license_expiry", "updated_at"])
            elif document.document_type == RegistryDocument.DocumentType.PROFESSIONAL_INDEMNITY:
                if practitioner.indemnity_expiry < today:
                    practitioner.indemnity_expiry = today
                practitioner.indemnity_expiry = practitioner.indemnity_expiry + relativedelta(years=1)
                practitioner.save(update_fields=["indemnity_expiry", "updated_at"])
            elif document.document_type == RegistryDocument.DocumentType.CPD_CERTIFICATE:
                points = getattr(django_settings, "CPD_RENEWAL_THRESHOLD", 50)
                practitioner.cpd_points = practitioner.cpd_points + points
                practitioner.save(update_fields=["cpd_points", "updated_at"])
        elif document.facility_id:
            facility = document.facility
            today = timezone.now().date()
            if document.document_type == RegistryDocument.DocumentType.FACILITY_ACCREDITATION:
                if facility.accreditation_expiry < today:
                    facility.accreditation_expiry = today
                facility.accreditation_expiry = facility.accreditation_expiry + relativedelta(years=1)
                facility.save(update_fields=["accreditation_expiry", "updated_at"])

    if document.practitioner_id:
        practitioner = document.practitioner
        practitioner.refresh_from_db()
        if practitioner.status == LicenseStatus.ACTIVE:
            issue_practitioner_certificate(practitioner, reviewed_by)

    if document.facility_id:
        facility = document.facility
        facility.refresh_from_db()
        if facility.status == LicenseStatus.ACTIVE:
            issue_facility_certificate(facility, reviewed_by)


def run_compliance_scan():
    """Flag expiring credentials and refresh practitioner compliance statuses."""
    today = timezone.now().date()
    horizon = today + timedelta(days=30)
    updated = 0
    for p in PractitionerProfile.objects.all():
        desired = derive_practitioner_status(p)
        if desired != p.status:
            set_practitioner_status(
                p,
                desired,
                None,
                reason="Automatic compliance scan update.",
            )
        updated += 1
        if p.license_expiry <= horizon and p.status == LicenseStatus.ACTIVE:
            try:
                user = p.user_account
                ComplianceAlert.objects.get_or_create(
                    alert_type=ComplianceAlert.AlertType.LICENSE_EXPIRING,
                    recipient=user,
                    related_practitioner=p,
                    title="Professional license expiring soon",
                    defaults={
                        "message": f"Your license expires on {p.license_expiry}. Complete renewal via NMALIS.",
                    },
                )
            except User.DoesNotExist:
                pass
    for f in HealthcareFacility.objects.all():
        desired = derive_facility_status(f)
        if desired != f.status:
            set_facility_status(
                f,
                desired,
                None,
                reason="Automatic compliance scan update.",
            )

    for f in HealthcareFacility.objects.filter(accreditation_expiry__lte=horizon, status=LicenseStatus.ACTIVE):
        for admin in User.objects.filter(role=User.Role.HOSPITAL_ADMIN, facility=f):
            ComplianceAlert.objects.get_or_create(
                alert_type=ComplianceAlert.AlertType.ACCREDITATION_EXPIRING,
                recipient=admin,
                related_facility=f,
                title="Facility accreditation expiring soon",
                defaults={
                    "message": f"Accreditation for {f.name} expires on {f.accreditation_expiry}.",
                },
            )
    return updated


def verify_practitioner(license_number: str, user) -> dict:
    try:
        p = PractitionerProfile.objects.get(license_number__iexact=license_number.strip())
    except PractitionerProfile.DoesNotExist:
        result = {
            "found": False,
            "status": "invalid",
            "color": "danger",
            "summary": "No practitioner found with that license number.",
            "practitioner": None,
        }
    else:
        p.refresh_compliance_status()
        result = {
            "found": True,
            "status": p.status,
            "color": p.status_color,
            "summary": _practitioner_summary(p),
            "practitioner": p,
        }
    VerificationCheck.objects.create(
        check_type=VerificationCheck.CheckType.DOCTOR_BY_ADMIN,
        performed_by=user,
        query_identifier=license_number.strip(),
        result_status=result["status"],
        result_summary=result["summary"],
    )
    return result


def verify_facility(registration_number: str, user) -> dict:
    try:
        f = HealthcareFacility.objects.get(registration_number__iexact=registration_number.strip())
    except HealthcareFacility.DoesNotExist:
        result = {
            "found": False,
            "status": "invalid",
            "color": "danger",
            "summary": "No facility found with that registration number.",
            "facility": None,
        }
    else:
        result = {
            "found": True,
            "status": f.status,
            "color": f.status_color,
            "summary": _facility_summary(f),
            "facility": f,
        }
    VerificationCheck.objects.create(
        check_type=VerificationCheck.CheckType.FACILITY_BY_DOCTOR,
        performed_by=user,
        query_identifier=registration_number.strip(),
        result_status=result["status"],
        result_summary=result["summary"],
    )
    return result


def _practitioner_summary(p: PractitionerProfile) -> str:
    parts = [
        f"{p.full_name} — {p.get_status_display()}.",
        f"License valid until {p.license_expiry}.",
        f"Indemnity until {p.indemnity_expiry}.",
        f"CPD points: {p.cpd_points} (threshold {getattr(django_settings, 'CPD_RENEWAL_THRESHOLD', 50)}).",
    ]
    if p.is_creditable:
        parts.append("Credibility check: PASSED — eligible for clinical practice.")
    else:
        parts.append("Credibility check: FAILED — do not assign clinical duties.")
    return " ".join(parts)


def _facility_summary(f: HealthcareFacility) -> str:
    parts = [
        f"{f.name} ({f.county}) — {f.get_status_display()}.",
        f"Accreditation valid until {f.accreditation_expiry}.",
    ]
    if f.is_creditable:
        parts.append("Credibility check: PASSED — facility is accredited for employment.")
    else:
        parts.append("Credibility check: FAILED — verify before accepting employment.")
    return " ".join(parts)
