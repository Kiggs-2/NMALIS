from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from .models import (
    FacilityApplication,
    HealthcareFacility,
    LicenseStatus,
    PractitionerProfile,
    RegistryDocument,
    StaffAffiliation,
    VerificationCheck,
)


def build_compliance_analytics():
    today = timezone.now().date()
    horizon = today + timedelta(days=30)

    practitioner_status = list(
        PractitionerProfile.objects.values("status")
        .annotate(count=Count("id"))
        .order_by("status")
    )
    facility_status = list(
        HealthcareFacility.objects.values("status")
        .annotate(count=Count("id"))
        .order_by("status")
    )
    document_review = list(
        RegistryDocument.objects.values("review_status")
        .annotate(count=Count("id"))
        .order_by("review_status")
    )

    return {
        "totals": {
            "practitioners": PractitionerProfile.objects.count(),
            "facilities": HealthcareFacility.objects.count(),
            "active_staff_affiliations": StaffAffiliation.objects.filter(is_active=True).count(),
            "pending_documents": RegistryDocument.objects.filter(
                review_status=RegistryDocument.ReviewStatus.PENDING
            ).count(),
            "pending_applications": FacilityApplication.objects.filter(
                status=FacilityApplication.ApplicationStatus.PENDING
            ).count(),
        },
        "practitioner_status": practitioner_status,
        "facility_status": facility_status,
        "document_review": document_review,
        "expiring_practitioner_licences": PractitionerProfile.objects.filter(
            license_expiry__lte=horizon,
            status=LicenseStatus.ACTIVE,
        ).count(),
        "expiring_facility_accreditations": HealthcareFacility.objects.filter(
            accreditation_expiry__lte=horizon,
            status=LicenseStatus.ACTIVE,
        ).count(),
        "non_compliant_practitioners": PractitionerProfile.objects.exclude(
            status=LicenseStatus.ACTIVE
        ).count(),
        "non_compliant_facilities": HealthcareFacility.objects.exclude(
            status=LicenseStatus.ACTIVE
        ).count(),
        "recent_verifications": VerificationCheck.objects.select_related("performed_by").order_by(
            "-created_at"
        )[:15],
        "pending_applications": FacilityApplication.objects.filter(
            status=FacilityApplication.ApplicationStatus.PENDING
        ).select_related("facility", "submitted_by"),
    }
