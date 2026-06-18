from django.http import FileResponse

from .models import ComplianceAlert, HealthcareFacility, LicenseStatus, PractitionerProfile, User


def practitioner_can_download(user, practitioner: PractitionerProfile) -> bool:
    if user.role == User.Role.REGULATOR:
        return True
    if user.role == User.Role.PRACTITIONER and user.practitioner_profile_id == practitioner.pk:
        return practitioner.status == LicenseStatus.ACTIVE
    return False


def facility_can_download(user, facility: HealthcareFacility) -> bool:
    if user.role == User.Role.REGULATOR:
        return True
    if user.role == User.Role.HOSPITAL_ADMIN and user.facility_id == facility.pk:
        return facility.status == LicenseStatus.ACTIVE
    return False


def issue_practitioner_certificate(practitioner: PractitionerProfile, issued_by):
    try:
        recipient = practitioner.user_account
    except User.DoesNotExist:
        return False
    ComplianceAlert.objects.get_or_create(
        alert_type=ComplianceAlert.AlertType.STATUS_CHANGED,
        recipient=recipient,
        related_practitioner=practitioner,
        title="Practising licence certificate issued",
        defaults={
            "message": (
                f"Your practising licence certificate ({practitioner.license_number}) is now available. "
                "Open your dashboard and download the PDF from My licence."
            ),
        },
    )
    return True


def issue_facility_certificate(facility: HealthcareFacility, issued_by):
    admins = User.objects.filter(role=User.Role.HOSPITAL_ADMIN, facility=facility)
    if not admins.exists():
        return False
    for admin in admins:
        ComplianceAlert.objects.get_or_create(
            alert_type=ComplianceAlert.AlertType.STATUS_CHANGED,
            recipient=admin,
            related_facility=facility,
            title="Facility accreditation certificate issued",
            defaults={
                "message": (
                    f"The accreditation certificate for {facility.name} ({facility.registration_number}) "
                    "is now available. Download it from your facility workspace."
                ),
            },
        )
    return True


def pdf_response(buffer, filename: str) -> FileResponse:
    return FileResponse(buffer, as_attachment=True, filename=filename, content_type="application/pdf")
