from django.utils import timezone

from .models import (
    ComplianceAlert,
    FacilityApplication,
    HealthcareFacility,
    RegistryDocument,
    User,
)
from .services import refresh_subject_statuses


def approve_facility_application(application: FacilityApplication, regulator):
    facility = application.facility
    application.status = FacilityApplication.ApplicationStatus.APPROVED
    application.reviewed_by = regulator
    application.reviewed_at = timezone.now()
    application.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])

    if application.application_type == FacilityApplication.ApplicationType.SERVICES_UPDATE:
        facility.services_offered = application.services_requested.strip()
        facility.save(update_fields=["services_offered", "updated_at"])
    elif application.application_type == FacilityApplication.ApplicationType.LICENCE_RENEWAL:
        facility.accreditation_expiry = application.accreditation_sought_until
        facility.county = application.county
        facility.name = application.facility_legal_name
        facility.save(
            update_fields=["accreditation_expiry", "county", "name", "updated_at"]
        )

    if application.supporting_file:
        RegistryDocument.objects.update_or_create(
            facility=facility,
            document_type=RegistryDocument.DocumentType.FACILITY_ACCREDITATION,
            reference_number=f"APP-{application.pk}",
            defaults={
                "title": application.get_application_type_display(),
                "file": application.supporting_file,
                "review_status": RegistryDocument.ReviewStatus.VERIFIED,
                "reviewed_by": regulator,
                "reviewed_at": timezone.now(),
                "expires_on": application.accreditation_sought_until,
            },
        )

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
        update_fields=["status", "review_notes", "reviewed_by", "reviewed_at", "updated_at"]
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
