from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile

from registry.models import (
    HealthcareFacility,
    LicenseStatus,
    PractitionerProfile,
    RegistryDocument,
    StaffAffiliation,
    User,
)


class Command(BaseCommand):
    help = "Load synthetic demo data for NMALIS (Dr. Sample, Test Clinic, etc.)"

    def handle(self, *args, **options):
        today = timezone.now().date()

        facility, _ = HealthcareFacility.objects.update_or_create(
            registration_number="FAC-KEN-001",
            defaults={
                "name": "Kabarak University Teaching Hospital (Demo)",
                "county": "Nakuru",
                "services_offered": "General Medicine, Surgery, Maternity",
                "status": LicenseStatus.ACTIVE,
                "accreditation_expiry": today + timedelta(days=365),
            },
        )

        ghost_facility, _ = HealthcareFacility.objects.update_or_create(
            registration_number="FAC-GHOST-999",
            defaults={
                "name": "Unaccredited Test Clinic",
                "county": "Nairobi",
                "services_offered": "Outpatient",
                "status": LicenseStatus.SUSPENDED,
                "accreditation_expiry": today - timedelta(days=30),
            },
        )

        practitioners_data = [
            {
                "license_number": "KMP-2024-001",
                "full_name": "Dr. Sample A Mwangi",
                "specialty": "General Practice",
                "status": LicenseStatus.ACTIVE,
                "license_expiry": today + timedelta(days=200),
                "indemnity_expiry": today + timedelta(days=200),
                "cpd_points": 55,
                "username": "doctor_sample",
            },
            {
                "license_number": "KMP-2023-442",
                "full_name": "Dr. Sample B Otieno",
                "specialty": "Paediatrics",
                "status": LicenseStatus.PENDING_RENEWAL,
                "license_expiry": today + timedelta(days=60),
                "indemnity_expiry": today + timedelta(days=90),
                "cpd_points": 35,
                "username": "doctor_pending",
            },
            {
                "license_number": "KMP-2022-118",
                "full_name": "Dr. Sample C Kariuki",
                "specialty": "Surgery",
                "status": LicenseStatus.SUSPENDED,
                "license_expiry": today + timedelta(days=100),
                "indemnity_expiry": today + timedelta(days=100),
                "cpd_points": 60,
                "username": "doctor_suspended",
            },
        ]

        password = "demo1234"
        for data in practitioners_data:
            username = data.pop("username")
            p, _ = PractitionerProfile.objects.update_or_create(
                license_number=data["license_number"],
                defaults=data,
            )
            user, created = User.objects.update_or_create(
                username=username,
                defaults={
                    "role": User.Role.PRACTITIONER,
                    "practitioner_profile": p,
                    "email": f"{username}@demo.nmalis.ke",
                    "first_name": p.full_name.split()[-1],
                },
            )
            if created:
                user.set_password(password)
                user.save()

        sample = PractitionerProfile.objects.get(license_number="KMP-2024-001")
        suspended = PractitionerProfile.objects.get(license_number="KMP-2022-118")

        StaffAffiliation.objects.update_or_create(
            practitioner=sample,
            facility=facility,
            defaults={"role_at_facility": "Consultant", "is_active": True},
        )
        StaffAffiliation.objects.update_or_create(
            practitioner=suspended,
            facility=facility,
            defaults={"role_at_facility": "Visiting Surgeon", "is_active": True},
        )

        regulator, created = User.objects.update_or_create(
            username="regulator",
            defaults={
                "role": User.Role.REGULATOR,
                "email": "regulator@kmpdc.demo.ke",
                "is_staff": True,
            },
        )
        if created:
            regulator.set_password(password)
            regulator.save()

        hospital_admin, created = User.objects.update_or_create(
            username="hospital_admin",
            defaults={
                "role": User.Role.HOSPITAL_ADMIN,
                "facility": facility,
                "email": "admin@test-hospital.demo.ke",
                "personal_physician": sample,
            },
        )
        if created:
            hospital_admin.set_password(password)
            hospital_admin.save()
        else:
            hospital_admin.personal_physician = sample
            hospital_admin.save(update_fields=["personal_physician"])

        self._seed_documents(sample, suspended, facility, ghost_facility, today)

        self.stdout.write(self.style.SUCCESS("Demo data loaded."))
        self.stdout.write("Login: regulator / hospital_admin / doctor_sample")
        self.stdout.write(f"Password: {password}")
        self.stdout.write(f"Verify ghost clinic: {ghost_facility.registration_number}")
        self.stdout.write(f"Verify Dr. Sample: {sample.license_number}")
        self.stdout.write("Regulator: Documents menu for license verification")

    def _seed_documents(self, sample, suspended, facility, ghost_facility, today):
        from registry.models import StatusChangeLog

        media_root = Path(settings.MEDIA_ROOT)
        media_root.mkdir(parents=True, exist_ok=True)

        demo_pdf = (
            b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
        )

        docs = [
            {
                "practitioner": sample,
                "document_type": RegistryDocument.DocumentType.PRACTITIONER_LICENSE,
                "title": "Annual Practising License 2024",
                "reference_number": f"{sample.license_number}-LIC",
                "expires_on": sample.license_expiry,
                "filename": f"{sample.license_number}_license.pdf",
                "review_status": RegistryDocument.ReviewStatus.VERIFIED,
            },
            {
                "practitioner": sample,
                "document_type": RegistryDocument.DocumentType.PROFESSIONAL_INDEMNITY,
                "title": "Professional Indemnity Cover — 2025",
                "reference_number": f"IND-{sample.license_number}",
                "expires_on": sample.indemnity_expiry,
                "filename": f"{sample.license_number}_indemnity.pdf",
                "review_status": RegistryDocument.ReviewStatus.VERIFIED,
            },
            {
                "practitioner": sample,
                "document_type": RegistryDocument.DocumentType.CPD_CERTIFICATE,
                "title": "CPD Completion Certificate — 40 Points",
                "reference_number": "CPD-2025-SAMPLE",
                "expires_on": today + timedelta(days=365),
                "filename": f"{sample.license_number}_cpd.pdf",
                "review_status": RegistryDocument.ReviewStatus.VERIFIED,
            },
            {
                "practitioner": sample,
                "document_type": RegistryDocument.DocumentType.INTERNSHIP_CERTIFICATE,
                "title": "Internship Completion Certificate",
                "reference_number": f"INT-{sample.license_number}",
                "expires_on": None,
                "filename": f"{sample.license_number}_internship.pdf",
                "review_status": RegistryDocument.ReviewStatus.VERIFIED,
            },
            {
                "practitioner": suspended,
                "document_type": RegistryDocument.DocumentType.PRACTITIONER_LICENSE,
                "title": "Practising License (under review)",
                "reference_number": suspended.license_number,
                "expires_on": suspended.license_expiry,
                "filename": f"{suspended.license_number}_license.pdf",
                "review_status": RegistryDocument.ReviewStatus.PENDING,
            },
            {
                "practitioner": suspended,
                "document_type": RegistryDocument.DocumentType.PROFESSIONAL_INDEMNITY,
                "title": "Professional Indemnity (expired)",
                "reference_number": f"IND-{suspended.license_number}",
                "expires_on": today - timedelta(days=30),
                "filename": f"{suspended.license_number}_indemnity.pdf",
                "review_status": RegistryDocument.ReviewStatus.REJECTED,
            },
            {
                "facility": facility,
                "document_type": RegistryDocument.DocumentType.FACILITY_ACCREDITATION,
                "title": "Facility Accreditation Certificate — Level 5",
                "reference_number": f"{facility.registration_number}-ACC",
                "expires_on": facility.accreditation_expiry,
                "filename": f"{facility.registration_number}_accreditation.pdf",
                "review_status": RegistryDocument.ReviewStatus.VERIFIED,
            },
            {
                "facility": facility,
                "document_type": RegistryDocument.DocumentType.OTHER,
                "title": "Health Inspectorate Compliance Report 2025",
                "reference_number": f"HIC-{facility.registration_number}",
                "expires_on": today + timedelta(days=180),
                "filename": f"{facility.registration_number}_inspection.pdf",
                "review_status": RegistryDocument.ReviewStatus.VERIFIED,
            },
            {
                "facility": ghost_facility,
                "document_type": RegistryDocument.DocumentType.FACILITY_ACCREDITATION,
                "title": "Expired accreditation submission",
                "reference_number": ghost_facility.registration_number,
                "expires_on": ghost_facility.accreditation_expiry,
                "filename": f"{ghost_facility.registration_number}_accreditation.pdf",
                "review_status": RegistryDocument.ReviewStatus.REJECTED,
            },
        ]

        for item in docs:
            filename = item.pop("filename")
            review_status = item.pop("review_status", RegistryDocument.ReviewStatus.PENDING)
            ref = item["reference_number"]
            doc, created = RegistryDocument.objects.update_or_create(
                reference_number=ref,
                defaults={**item, "review_status": review_status},
            )
            if not doc.file:
                doc.file.save(filename, ContentFile(demo_pdf), save=True)

        # Seed some status change logs
        regulator = User.objects.filter(role=User.Role.REGULATOR).first()
        if regulator:
            StatusChangeLog.objects.get_or_create(
                entity_type="practitioner",
                entity_id=sample.pk,
                entity_label=str(sample),
                defaults={
                    "old_status": LicenseStatus.PENDING_RENEWAL,
                    "new_status": LicenseStatus.ACTIVE,
                    "reason": "Automatic compliance check: all documents verified and expiry dates valid.",
                    "changed_by": regulator,
                    "created_at": today - timedelta(days=60),
                },
            )
            StatusChangeLog.objects.get_or_create(
                entity_type="practitioner",
                entity_id=suspended.pk,
                entity_label=str(suspended),
                defaults={
                    "old_status": LicenseStatus.ACTIVE,
                    "new_status": LicenseStatus.SUSPENDED,
                    "reason": "Document rejected: Professional Indemnity certificate expired.",
                    "accountability_confirmed": True,
                    "changed_by": regulator,
                    "created_at": today - timedelta(days=7),
                },
            )
            StatusChangeLog.objects.get_or_create(
                entity_type="facility",
                entity_id=ghost_facility.pk,
                entity_label=str(ghost_facility),
                defaults={
                    "old_status": LicenseStatus.ACTIVE,
                    "new_status": LicenseStatus.SUSPENDED,
                    "reason": "Accreditation expired and renewal rejected — facility does not meet minimum standards.",
                    "accountability_confirmed": True,
                    "changed_by": regulator,
                    "created_at": today - timedelta(days=14),
                },
            )
