from dateutil.relativedelta import relativedelta
from django.utils import timezone

from .models import (
    ComplianceAlert,
    FacilityApplication,
    HealthcareFacility,
    PractitionerProfile,
    PractitionerRenewalApplication,
    RegistryDocument,
    User,
)
from .services import apply_document_review_outcome, refresh_subject_statuses


def approve_facility_application(application: FacilityApplication, regulator):
    facility = application.facility
    application.status = FacilityApplication.ApplicationStatus.APPROVED
    application.reviewed_by = regulator
    application.reviewed_at = timezone.now()
    application.save(update_fields=["status", "reviewed_by", "reviewed_at"])

    if application.application_type == FacilityApplication.ApplicationType.SERVICES_UPDATE:
        facility.services_offered = application.services_requested.strip()
        facility.save(update_fields=["services_offered", "updated_at"])
        doc, _ = RegistryDocument.objects.update_or_create(
            facility=facility,
            document_type=RegistryDocument.DocumentType.FACILITY_ACCREDITATION,
            reference_number=f"APP-{application.pk}",
            defaults={
                "title": "Services update — approved",
                "review_status": RegistryDocument.ReviewStatus.VERIFIED,
                "reviewed_by": regulator,
                "reviewed_at": timezone.now(),
            },
        )
        apply_document_review_outcome(doc, regulator)
    elif application.application_type == FacilityApplication.ApplicationType.LICENCE_RENEWAL:
        facility.county = application.county
        facility.name = application.facility_legal_name
        facility.save(update_fields=["county", "name", "updated_at"])
        doc_defaults = {
            "title": application.get_application_type_display(),
            "review_status": RegistryDocument.ReviewStatus.VERIFIED,
            "reviewed_by": regulator,
            "reviewed_at": timezone.now(),
        }
        if application.supporting_file:
            doc_defaults["file"] = application.supporting_file
            doc_defaults["expires_on"] = facility.accreditation_expiry
        doc, _ = RegistryDocument.objects.update_or_create(
            facility=facility,
            document_type=RegistryDocument.DocumentType.FACILITY_ACCREDITATION,
            reference_number=f"APP-{application.pk}",
            defaults=doc_defaults,
        )
        apply_document_review_outcome(doc, regulator)

    refresh_subject_statuses(triggered_by=regulator)
    _notify_facility_admins(
        facility,
        f"Application approved: {application.get_application_type_display()}",
        f"Your submission for {facility.name} was approved. Registry records have been updated.",
    )


def reject_facility_application(application: FacilityApplication, regulator, notes: str):
    application.status = FacilityApplication.ApplicationStatus.REJECTED
    application.review_notes = notes
    application.reviewed_by = regulator
    application.reviewed_at = timezone.now()
    application.save(
        update_fields=["status", "review_notes", "reviewed_by", "reviewed_at"]
    )
    _notify_facility_admins(
        application.facility,
        f"Application rejected: {application.get_application_type_display()}",
        notes or "Your application was rejected. Contact KMPDC for guidance.",
    )


def _notify_facility_admins(facility: HealthcareFacility, title: str, message: str):
    for admin in User.objects.filter(role=User.Role.HOSPITAL_ADMIN, facility=facility):
        ComplianceAlert.objects.create(
            alert_type=ComplianceAlert.AlertType.STATUS_CHANGED,
            recipient=admin,
            title=title,
            message=message,
            related_facility=facility,
        )


def approve_practitioner_application(application: PractitionerRenewalApplication, regulator):
    application.status = PractitionerRenewalApplication.ApplicationStatus.APPROVED
    application.reviewed_by = regulator
    application.reviewed_at = timezone.now()
    application.save(update_fields=["status", "reviewed_by", "reviewed_at"])

    refresh_subject_statuses(triggered_by=regulator)
    _notify_practitioner(
        application.practitioner,
        "Practitioner licence renewal approved",
        "Your renewal application was approved. Once your supporting documents are verified, your licence and CPD will be updated automatically.",
    )


def reject_practitioner_application(application: PractitionerRenewalApplication, regulator, notes: str):
    application.status = PractitionerRenewalApplication.ApplicationStatus.REJECTED
    application.review_notes = notes
    application.reviewed_by = regulator
    application.reviewed_at = timezone.now()
    application.save(
        update_fields=["status", "review_notes", "reviewed_by", "reviewed_at"]
    )
    _notify_practitioner(
        application.practitioner,
        "Practitioner licence renewal rejected",
        notes or "Your renewal application was rejected. Contact KMPDC for guidance.",
    )


def _notify_practitioner(practitioner: PractitionerProfile, title: str, message: str):
    user_account = practitioner.user_account
    if user_account:
        ComplianceAlert.objects.create(
            alert_type=ComplianceAlert.AlertType.STATUS_CHANGED,
            recipient=user_account,
            title=title,
            message=message,
            related_practitioner=practitioner,
        )
