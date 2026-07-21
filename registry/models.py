from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


class User(AbstractUser):
    class Role(models.TextChoices):
        REGULATOR = "regulator", "Regulator (KMPDC)"
        HOSPITAL_ADMIN = "hospital_admin", "Hospital Administrator"
        PRACTITIONER = "practitioner", "Medical Practitioner"
        SYSTEM_ADMIN = "system_admin", "System Administrator"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.PRACTITIONER)
    facility = models.ForeignKey(
        "HealthcareFacility",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admin_users",
    )
    practitioner_profile = models.OneToOneField(
        "PractitionerProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_account",
    )
    personal_physician = models.ForeignKey(
        "PractitionerProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hospital_admin_patients",
        help_text="Hospital admin's linked personal physician for quick access.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("username"),
                name="uniq_user_username_ci",
            ),
        ]

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class LicenseStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    PENDING_RENEWAL = "pending_renewal", "Pending Renewal"
    SUSPENDED = "suspended", "Suspended"
    REVOKED = "revoked", "Revoked"
    EXPIRED = "expired", "Expired"


class HealthcareFacility(models.Model):
    registration_number = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=255)
    county = models.CharField(max_length=64, blank=True)
    services_offered = models.TextField(blank=True, help_text="Comma-separated services")
    status = models.CharField(
        max_length=20,
        choices=LicenseStatus.choices,
        default=LicenseStatus.ACTIVE,
    )
    accreditation_expiry = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Healthcare facilities"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                Lower("registration_number"),
                name="uniq_facility_registration_number_ci",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.registration_number})"

    @property
    def status_color(self):
        return status_badge_color(self.status)

    @property
    def is_creditable(self):
        return self.status == LicenseStatus.ACTIVE and self.accreditation_expiry >= timezone.now().date()


class PractitionerProfile(models.Model):
    license_number = models.CharField(max_length=32, unique=True)
    full_name = models.CharField(max_length=255)
    specialty = models.CharField(max_length=128, blank=True)
    status = models.CharField(
        max_length=20,
        choices=LicenseStatus.choices,
        default=LicenseStatus.ACTIVE,
    )
    license_expiry = models.DateField()
    indemnity_expiry = models.DateField()
    cpd_points = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name"]
        constraints = [
            models.UniqueConstraint(
                Lower("license_number"),
                name="uniq_practitioner_license_number_ci",
            ),
        ]

    def __str__(self):
        return f"{self.full_name} ({self.license_number})"

    @property
    def status_color(self):
        return status_badge_color(self.status)

    @property
    def cpd_meets_threshold(self):
        return self.cpd_points >= getattr(settings, "CPD_RENEWAL_THRESHOLD", 50)

    @property
    def is_creditable(self):
        today = timezone.now().date()
        if self.status != LicenseStatus.ACTIVE:
            return False
        if self.license_expiry < today or self.indemnity_expiry < today:
            return False
        return self.cpd_meets_threshold

    def refresh_compliance_status(self):
        """Automated compliance engine: update status from dates and CPD."""
        today = timezone.now().date()
        if self.status in (LicenseStatus.SUSPENDED, LicenseStatus.REVOKED):
            return False
        previous = self.status
        if self.license_expiry < today or self.indemnity_expiry < today:
            self.status = LicenseStatus.EXPIRED
        elif not self.cpd_meets_threshold:
            self.status = LicenseStatus.PENDING_RENEWAL
        elif self.status in (LicenseStatus.EXPIRED, LicenseStatus.PENDING_RENEWAL):
            self.status = LicenseStatus.ACTIVE
        if self.status != previous:
            self.save(update_fields=["status", "updated_at"])
            return True
        return False


def default_start_date():
    return timezone.localdate()


class StaffAffiliation(models.Model):
    practitioner = models.ForeignKey(
        PractitionerProfile,
        on_delete=models.CASCADE,
        related_name="affiliations",
    )
    facility = models.ForeignKey(
        HealthcareFacility,
        on_delete=models.CASCADE,
        related_name="staff_affiliations",
    )
    role_at_facility = models.CharField(max_length=128, blank=True)
    start_date = models.DateField(default=default_start_date)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("practitioner", "facility", "start_date")]
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.practitioner} @ {self.facility}"


class RegistryDocument(models.Model):
    class DocumentType(models.TextChoices):
        PRACTITIONER_LICENSE = "practitioner_license", "Practitioner license"
        PROFESSIONAL_INDEMNITY = "professional_indemnity", "Professional indemnity"
        CPD_CERTIFICATE = "cpd_certificate", "CPD certificate"
        FACILITY_ACCREDITATION = "facility_accreditation", "Facility accreditation"
        INTERNSHIP_CERTIFICATE = "internship_certificate", "Internship certificate"
        OTHER = "other", "Other supporting document"

    class ReviewStatus(models.TextChoices):
        PENDING = "pending", "Pending review"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"

    document_type = models.CharField(max_length=32, choices=DocumentType.choices)
    title = models.CharField(max_length=255)
    reference_number = models.CharField(max_length=64, blank=True)
    file = models.FileField(upload_to="registry_documents/%Y/%m/", blank=True)
    practitioner = models.ForeignKey(
        PractitionerProfile,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="documents",
    )
    facility = models.ForeignKey(
        HealthcareFacility,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="documents",
    )
    review_status = models.CharField(
        max_length=16,
        choices=ReviewStatus.choices,
        default=ReviewStatus.PENDING,
    )
    review_notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_documents",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    expires_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-submitted_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["practitioner", "document_type", "reference_number"],
                name="uniq_practitioner_document_record",
            ),
            models.UniqueConstraint(
                fields=["facility", "document_type", "reference_number"],
                name="uniq_facility_document_record",
            ),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_review_status_display()})"

    @property
    def subject_label(self):
        if self.practitioner_id:
            return str(self.practitioner)
        if self.facility_id:
            return str(self.facility)
        return "Unlinked"

    @property
    def review_badge_color(self):
        return {
            self.ReviewStatus.PENDING: "warning",
            self.ReviewStatus.VERIFIED: "success",
            self.ReviewStatus.REJECTED: "danger",
        }.get(self.review_status, "secondary")


class StatusChangeLog(models.Model):
    entity_type = models.CharField(max_length=32)  # practitioner | facility
    entity_id = models.PositiveIntegerField()
    entity_label = models.CharField(max_length=255)
    old_status = models.CharField(max_length=20, blank=True)
    new_status = models.CharField(max_length=20)
    reason = models.TextField(blank=True)
    accountability_confirmed = models.BooleanField(default=False)
    accountability_statement = models.CharField(max_length=500, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="status_changes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.entity_label}: {self.old_status} -> {self.new_status}"


class VerificationCheck(models.Model):
    class CheckType(models.TextChoices):
        DOCTOR_BY_ADMIN = "doctor_by_admin", "Doctor credibility check"
        FACILITY_BY_DOCTOR = "facility_by_doctor", "Hospital credibility check"

    check_type = models.CharField(max_length=32, choices=CheckType.choices)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="verification_checks",
    )
    query_identifier = models.CharField(max_length=64)
    result_status = models.CharField(max_length=20)
    result_summary = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.check_type} by {self.performed_by.username}"


class FacilityApplication(models.Model):
    class ApplicationType(models.TextChoices):
        LICENCE_RENEWAL = "licence_renewal", "Facility licence renewal / application"
        SERVICES_UPDATE = "services_update", "Update of services offered"

    class ApplicationStatus(models.TextChoices):
        PENDING = "pending", "Pending regulator review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    facility = models.ForeignKey(
        HealthcareFacility,
        on_delete=models.CASCADE,
        related_name="applications",
    )
    application_type = models.CharField(max_length=32, choices=ApplicationType.choices)
    status = models.CharField(
        max_length=16,
        choices=ApplicationStatus.choices,
        default=ApplicationStatus.PENDING,
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="facility_applications",
    )
    facility_legal_name = models.CharField(max_length=255)
    registration_number = models.CharField(max_length=32)
    county = models.CharField(max_length=64)
    physical_address = models.CharField(max_length=255)
    postal_address = models.CharField(max_length=255, blank=True)
    telephone = models.CharField(max_length=32)
    email = models.EmailField()
    director_name = models.CharField(max_length=255, verbose_name="Director of medical services")
    bed_capacity = models.PositiveIntegerField(default=0)
    services_requested = models.TextField(help_text="Services to be offered or updated")
    accreditation_sought_until = models.DateField()
    declaration_agreed = models.BooleanField(default=False)
    supporting_file = models.FileField(upload_to="facility_applications/%Y/%m/", blank=True)
    review_notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_facility_applications",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["facility", "application_type"],
                condition=models.Q(status="pending"),
                name="uniq_facility_pending_application_type",
            ),
        ]

    def __str__(self):
        return f"{self.get_application_type_display()} — {self.facility_legal_name}"

    @property
    def status_color(self):
        return {
            self.ApplicationStatus.PENDING: "warning",
            self.ApplicationStatus.APPROVED: "success",
            self.ApplicationStatus.REJECTED: "danger",
        }.get(self.status, "secondary")


class PractitionerRenewalApplication(models.Model):
    """Stores renewal application form data submitted by a practitioner."""
    practitioner = models.ForeignKey(
        PractitionerProfile,
        on_delete=models.CASCADE,
        related_name="renewal_applications",
    )
    submitted_at = models.DateTimeField(default=timezone.now)

    # Renewal form fields
    current_employer = models.CharField(max_length=255, blank=True)
    work_contact_phone = models.CharField(max_length=32, blank=True)
    work_email = models.EmailField(blank=True)
    has_practised_continuously = models.CharField(max_length=8, blank=True)
    practice_break_reason = models.TextField(blank=True)
    has_malpractice_history = models.CharField(max_length=8, blank=True)
    malpractice_details = models.TextField(blank=True)

    class Meta:
        ordering = ["-submitted_at"]
        verbose_name = "Practitioner renewal application"

    def __str__(self):
        return f"Renewal by {self.practitioner} @ {self.submitted_at.date()}"


class PractitionerRenewalPayment(models.Model):
    """Tracks M-Pesa Daraja payments for practitioner licence renewal.

    The workflow expects practitioners to pay the renewal fee first. Once a payment
    is confirmed (status="completed"), the practitioner may submit their renewal
    application.
    """
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    practitioner = models.ForeignKey(
        PractitionerProfile,
        on_delete=models.CASCADE,
        related_name="renewal_payments",
    )
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="initiated_payments",
    )
    phone_number = models.CharField(max_length=32)
    amount = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    merchant_request_id = models.CharField(max_length=128, blank=True)
    checkout_request_id = models.CharField(max_length=128, blank=True)
    mpesa_receipt_number = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["practitioner"],
                condition=models.Q(status__in=["pending", "completed"]),
                name="uniq_practitioner_active_payment",
            ),
        ]

    def __str__(self):
        return f"M-Pesa payment ({self.amount}) for {self.practitioner} — {self.status}"


class FacilityRenewalPayment(models.Model):
    """Tracks M-Pesa Daraja payments for facility licence renewal/application.

    Workflow mirrors PractitionerRenewalPayment but links to HealthcareFacility.
    """
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    class PaymentType(models.TextChoices):
        LICENCE_RENEWAL = "licence_renewal", "Licence renewal"
        SERVICES_UPDATE = "services_update", "Services update"

    facility = models.ForeignKey(
        HealthcareFacility,
        on_delete=models.CASCADE,
        related_name="renewal_payments",
    )
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="initiated_facility_payments",
    )
    phone_number = models.CharField(max_length=32)
    amount = models.PositiveIntegerField()
    payment_type = models.CharField(max_length=32, choices=PaymentType.choices, default=PaymentType.LICENCE_RENEWAL)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    merchant_request_id = models.CharField(max_length=128, blank=True)
    checkout_request_id = models.CharField(max_length=128, blank=True)
    mpesa_receipt_number = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["facility", "payment_type"],
                condition=models.Q(status__in=["pending", "completed"]),
                name="uniq_facility_active_payment_type",
            ),
        ]

    def __str__(self):
        return f"M-Pesa payment ({self.amount}) for {self.facility} — {self.status}"


class ComplianceAlert(models.Model):
    class AlertType(models.TextChoices):
        LICENSE_EXPIRING = "license_expiring", "License expiring soon"
        ACCREDITATION_EXPIRING = "accreditation_expiring", "Accreditation expiring soon"
        STATUS_CHANGED = "status_changed", "Status changed"
        STAFF_NON_COMPLIANT = "staff_non_compliant", "Staff non-compliant"

    alert_type = models.CharField(max_length=32, choices=AlertType.choices)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="compliance_alerts",
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    related_practitioner = models.ForeignKey(
        PractitionerProfile,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    related_facility = models.ForeignKey(
        HealthcareFacility,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


def status_label(status: str) -> str:
    for choice_group in (LicenseStatus, PractitionerRenewalPayment.Status, FacilityRenewalPayment.Status):
        if status in dict(choice_group.choices):
            return dict(choice_group.choices)[status]
    return status.replace("_", " ").title()


def status_badge_color(status: str) -> str:
    mapping = {
        LicenseStatus.ACTIVE: "success",
        LicenseStatus.PENDING_RENEWAL: "warning",
        LicenseStatus.SUSPENDED: "danger",
        LicenseStatus.REVOKED: "danger",
        LicenseStatus.EXPIRED: "secondary",
        "invalid": "danger",
        PractitionerRenewalPayment.Status.COMPLETED: "success",
        PractitionerRenewalPayment.Status.PENDING: "warning",
        PractitionerRenewalPayment.Status.FAILED: "danger",
        FacilityRenewalPayment.Status.COMPLETED: "success",
        FacilityRenewalPayment.Status.PENDING: "warning",
        FacilityRenewalPayment.Status.FAILED: "danger",
    }
    return mapping.get(status, "secondary")
