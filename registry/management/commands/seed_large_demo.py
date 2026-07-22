"""Load a large synthetic dataset efficiently for testing with dynamic ReportLab PDFs."""

import io
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from registry.models import (
    FacilityApplication,
    HealthcareFacility,
    LicenseStatus,
    PractitionerProfile,
    RegistryDocument,
    StaffAffiliation,
    User,
)


def generate_pdf_bytes(title: str, reference: str, subtitle: str = "", doc_type: str = "") -> bytes:
    """Helper function to build a valid, viewable PDF in memory using ReportLab."""
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)

    # Header Title
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, 730, title)

    # Subtitle / Subject Name
    if subtitle:
        p.setFont("Helvetica-Bold", 12)
        p.drawString(100, 705, f"Subject: {subtitle}")

    # Metadata Block
    p.setFont("Helvetica", 10)
    p.drawString(100, 675, f"Reference Number: {reference}")
    if doc_type:
        p.drawString(100, 655, f"Document Type: {doc_type}")
    
    p.drawString(100, 635, f"Generated On: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Visual Separator
    p.setLineWidth(1)
    p.line(100, 620, 500, 620)

    # Document Body / Disclaimer
    p.setFont("Helvetica-Oblique", 10)
    p.drawString(100, 590, "This is an official system-generated test document for database seeding.")
    p.drawString(100, 575, "All data contained herein is synthetic and generated automatically.")

    # Page Footer
    p.setFont("Helvetica", 8)
    p.drawString(100, 50, "National Medical Portal — System Generated Copy")

    p.showPage()
    p.save()

    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


class Command(BaseCommand):
    help = "Load large demo dataset (facilities, practitioners, staff, documents, applications)"

    @transaction.atomic
    def handle(self, *args, **options):
        today = timezone.now().date()
        password = "demo1234"
        media_root = Path(settings.MEDIA_ROOT)
        media_root.mkdir(parents=True, exist_ok=True)

        counties = [
            "Nairobi", "Nakuru", "Mombasa", "Kisumu", "Uasin Gishu",
            "Kiambu", "Machakos", "Nyeri", "Kakamega", "Meru",
        ]
        specialties = [
            "General Practice", "Surgery", "Paediatrics", "Obstetrics",
            "Radiology", "Anaesthesia", "Internal Medicine", "Orthopaedics",
        ]
        services_pool = [
            "General Medicine, Outpatient",
            "Surgery, Maternity, Laboratory",
            "Paediatrics, Immunization, Emergency",
            "Radiology, Laboratory, Pharmacy",
        ]

        # Queue tracking documents to generate files dynamically
        documents_to_file = []

        # --- 1. SEED FACILITIES ---
        facilities = []
        for i in range(1, 31):
            reg = f"FAC-KEN-{i:03d}"
            facility, _ = HealthcareFacility.objects.update_or_create(
                registration_number=reg,
                defaults={
                    "name": f"Sample Health Centre {i}",
                    "county": counties[i % len(counties)],
                    "services_offered": services_pool[i % len(services_pool)],
                    "status": LicenseStatus.ACTIVE if i % 7 != 0 else LicenseStatus.SUSPENDED,
                    "accreditation_expiry": today + timedelta(days=90 + (i * 11) % 400),
                },
            )
            facilities.append(facility)

        # --- 2. SEED PRACTITIONERS ---
        practitioners = []
        first_names = ["Sample A", "Sample B", "Sample C", "Sample D", "Sample E"]
        last_names = ["Mwangi", "Otieno", "Kariuki", "Wanjiku", "Mutua", "Njeri", "Kamau", "Achieng"]
        for i in range(1, 81):
            lic = f"KMP-LRG-{i:03d}"
            fn = first_names[i % len(first_names)]
            ln = last_names[i % len(last_names)]
            status = LicenseStatus.ACTIVE
            if i % 13 == 0:
                status = LicenseStatus.SUSPENDED
            elif i % 9 == 0:
                status = LicenseStatus.PENDING_RENEWAL
            elif i % 17 == 0:
                status = LicenseStatus.EXPIRED

            p, _ = PractitionerProfile.objects.update_or_create(
                license_number=lic,
                defaults={
                    "full_name": f"Dr. {fn} {ln}",
                    "specialty": specialties[i % len(specialties)],
                    "status": status,
                    "license_expiry": today + timedelta(days=30 + (i * 7) % 500),
                    "indemnity_expiry": today + timedelta(days=40 + (i * 5) % 500),
                    "cpd_points": 30 + (i * 3) % 50,
                },
            )
            practitioners.append(p)

        sample_main = practitioners[0]

        # --- 3. SEED DOCTOR USERS ---
        for idx, p in enumerate(practitioners[1:16], start=2):
            u, created = User.objects.get_or_create(
                username=f"doctor_{idx:02d}",
                defaults={
                    "role": User.Role.PRACTITIONER,
                    "practitioner_profile": p,
                    "email": f"doctor_{idx:02d}@demo.nmalis.ke",
                    "is_active": True,
                },
            )
            if created:
                u.set_password(password)
                u.save()

        # --- 4. AFFILIATIONS & PRACTITIONER DOCUMENTS ---
        for i, p in enumerate(practitioners):
            fac = facilities[i % len(facilities)]
            StaffAffiliation.objects.update_or_create(
                practitioner=p,
                facility=fac,
                defaults={
                    "role_at_facility": specialties[i % len(specialties)],
                    "is_active": True,
                },
            )
            for j, doc_type in enumerate(
                [
                    RegistryDocument.DocumentType.PRACTITIONER_LICENSE,
                    RegistryDocument.DocumentType.PROFESSIONAL_INDEMNITY,
                    RegistryDocument.DocumentType.CPD_CERTIFICATE,
                ]
            ):
                ref = f"{p.license_number}-DOC-{j}"
                review = RegistryDocument.ReviewStatus.PENDING
                if i % 5 == 0 and j == 0:
                    review = RegistryDocument.ReviewStatus.REJECTED
                elif i % 3 != 0:
                    review = RegistryDocument.ReviewStatus.VERIFIED

                doc, _ = RegistryDocument.objects.update_or_create(
                    practitioner=p,
                    document_type=doc_type,
                    reference_number=ref,
                    defaults={
                        "title": f"{doc_type.replace('_', ' ').title()} — {p.full_name}",
                        "review_status": review,
                        "expires_on": today + timedelta(days=200),
                    },
                )
                if not doc.file:
                    documents_to_file.append((doc, ref, p.full_name))

        # --- 5. FACILITY DOCUMENTS ---
        for i, facility in enumerate(facilities):
            ref = f"{facility.registration_number}-ACC"
            review = RegistryDocument.ReviewStatus.VERIFIED if i % 4 else RegistryDocument.ReviewStatus.PENDING
            doc, _ = RegistryDocument.objects.update_or_create(
                facility=facility,
                document_type=RegistryDocument.DocumentType.FACILITY_ACCREDITATION,
                reference_number=ref,
                defaults={
                    "title": f"Accreditation — {facility.name}",
                    "review_status": review,
                    "expires_on": facility.accreditation_expiry,
                },
            )
            if not doc.file:
                documents_to_file.append((doc, ref, facility.name))

        # --- 6. REGULATOR ACCOUNT ---
        regulator, _ = User.objects.update_or_create(
            username="regulator",
            defaults={
                "role": User.Role.REGULATOR,
                "email": "regulator@kmpdc.demo.ke",
                "is_staff": True,
                "is_active": True,
            },
        )
        regulator.set_password(password)
        regulator.save()

        # --- 7. HOSPITAL ADMIN ACCOUNTS ---
        hospital_admin, _ = User.objects.update_or_create(
            username="hospital_admin",
            defaults={
                "role": User.Role.HOSPITAL_ADMIN,
                "facility": facilities[0],
                "email": "admin@test-hospital.demo.ke",
                "personal_physician": sample_main,
                "is_active": True,
            },
        )
        hospital_admin.set_password(password)
        hospital_admin.save()

        for i in range(1, 6):
            admin, _ = User.objects.update_or_create(
                username=f"hospital_admin_{i}",
                defaults={
                    "role": User.Role.HOSPITAL_ADMIN,
                    "facility": facilities[i],
                    "email": f"hospital_admin_{i}@demo.nmalis.ke",
                    "personal_physician": practitioners[i * 3],
                    "is_active": True,
                },
            )
            admin.set_password(password)
            admin.save()

        # --- 8. SAMPLE DOCTOR ACCOUNT ---
        doc_sample, _ = User.objects.update_or_create(
            username="doctor_sample",
            defaults={
                "role": User.Role.PRACTITIONER,
                "practitioner_profile": sample_main,
                "email": "doctor_sample@demo.nmalis.ke",
                "is_active": True,
            },
        )
        doc_sample.set_password(password)
        doc_sample.save()

        # --- 9. FACILITY APPLICATIONS ---
        for i in range(3):
            app, _ = FacilityApplication.objects.update_or_create(
                facility=facilities[i + 1],
                application_type=FacilityApplication.ApplicationType.SERVICES_UPDATE,
                status=FacilityApplication.ApplicationStatus.PENDING,
                defaults={
                    "submitted_by": hospital_admin,
                    "facility_legal_name": facilities[i + 1].name,
                    "registration_number": facilities[i + 1].registration_number,
                    "county": facilities[i + 1].county,
                    "physical_address": f"{facilities[i + 1].name}, {facilities[i + 1].county}",
                    "telephone": f"+25470000{i:04d}",
                    "email": f"facility{i}@demo.ke",
                    "director_name": f"Dr. Sample Director {i}",
                    "bed_capacity": 40 + i * 10,
                    "services_requested": "General Medicine, Surgery, ICU, Dialysis",
                    "accreditation_sought_until": today + timedelta(days=365),
                    "declaration_agreed": True,
                },
            )
            ref = f"APP-{facilities[i + 1].registration_number}-{app.pk}"
            doc, _ = RegistryDocument.objects.update_or_create(
                facility=facilities[i + 1],
                document_type=RegistryDocument.DocumentType.FACILITY_ACCREDITATION,
                reference_number=ref,
                defaults={
                    "title": "Services update — supporting document",
                    "review_status": RegistryDocument.ReviewStatus.PENDING,
                },
            )
            if not doc.file:
                documents_to_file.append((doc, ref, facilities[i + 1].name))

        approved_app, _ = FacilityApplication.objects.update_or_create(
            facility=facilities[1],
            application_type=FacilityApplication.ApplicationType.SERVICES_UPDATE,
            status=FacilityApplication.ApplicationStatus.APPROVED,
            defaults={
                "submitted_by": hospital_admin,
                "facility_legal_name": facilities[1].name,
                "registration_number": facilities[1].registration_number,
                "county": facilities[1].county,
                "physical_address": f"{facilities[1].name}, {facilities[1].county}",
                "telephone": "+254700000001",
                "email": "facility0@demo.ke",
                "director_name": "Dr. Sample Director 0",
                "bed_capacity": 40,
                "services_requested": "General Medicine, Surgery, ICU, Dialysis, Radiology",
                "accreditation_sought_until": today + timedelta(days=365),
                "declaration_agreed": True,
                "reviewed_by": regulator,
                "reviewed_at": timezone.now(),
            },
        )

        app_doc_ref = f"APP-{approved_app.pk}"
        app_doc, _ = RegistryDocument.objects.update_or_create(
            facility=facilities[1],
            document_type=RegistryDocument.DocumentType.FACILITY_ACCREDITATION,
            reference_number=app_doc_ref,
            defaults={
                "title": "Services update — approved",
                "review_status": RegistryDocument.ReviewStatus.VERIFIED,
                "reviewed_by": regulator,
                "reviewed_at": timezone.now(),
            },
        )
        if not app_doc.file:
            documents_to_file.append((app_doc, app_doc_ref, facilities[1].name))

        rejected_renewal, _ = FacilityApplication.objects.update_or_create(
            facility=facilities[2],
            application_type=FacilityApplication.ApplicationType.LICENCE_RENEWAL,
            status=FacilityApplication.ApplicationStatus.REJECTED,
            defaults={
                "submitted_by": hospital_admin,
                "facility_legal_name": facilities[2].name,
                "registration_number": facilities[2].registration_number,
                "county": facilities[2].county,
                "physical_address": f"{facilities[2].name}, {facilities[2].county}",
                "telephone": "+254700000002",
                "email": "facility1@demo.ke",
                "director_name": "Dr. Sample Director 1",
                "bed_capacity": 60,
                "services_requested": facilities[2].services_offered,
                "accreditation_sought_until": facilities[2].accreditation_expiry,
                "declaration_agreed": True,
                "reviewed_by": regulator,
                "reviewed_at": timezone.now(),
                "review_notes": "Incomplete supporting documents. Resubmit with full accreditation report.",
            },
        )

        # --- 10. SYSTEM ADMIN ACCOUNT ---
        sysadmin, _ = User.objects.update_or_create(
            username="sysadmin",
            defaults={
                "role": User.Role.SYSTEM_ADMIN,
                "email": "sysadmin@nmalis.ke",
                "first_name": "System",
                "last_name": "Administrator",
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            },
        )
        sysadmin.set_password(password)
        sysadmin.save()

        # --- 11. BATCH GENERATE & ATTACH REPORTLAB PDFS ---
        self.stdout.write("Generating ReportLab PDFs...")
        for doc, ref, subtitle in documents_to_file:
            pdf_bytes = generate_pdf_bytes(
                title=doc.title,
                reference=ref,
                subtitle=subtitle,
                doc_type=doc.get_document_type_display(),
            )
            filename = f"{ref}.pdf"
            doc.file.save(filename, ContentFile(pdf_bytes, name=filename), save=True)

        # --- OUTPUT CONSOLE SUMMARY ---
        self.stdout.write(self.style.SUCCESS("Large demo dataset loaded successfully with valid ReportLab PDFs."))
        self.stdout.write(f"Facilities: {len(facilities)} | Practitioners: {len(practitioners)}")
        self.stdout.write("--------------------------------------------------")
        self.stdout.write(f"Default Login Password: {password}")
        self.stdout.write("Available Accounts:")
        self.stdout.write("  - sysadmin         (System Admin / Superuser)")
        self.stdout.write("  - regulator        (Regulator / KMPDC)")
        self.stdout.write("  - hospital_admin   (Hospital Admin)")
        self.stdout.write("  - doctor_sample    (Practitioner)")
        self.stdout.write("  - doctor_02 ... doctor_15")
        self.stdout.write("--------------------------------------------------")