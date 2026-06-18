"""Load a large synthetic dataset for rigorous testing."""

from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone

from registry.models import (
    FacilityApplication,
    HealthcareFacility,
    LicenseStatus,
    PractitionerProfile,
    RegistryDocument,
    StaffAffiliation,
    User,
)


class Command(BaseCommand):
    help = "Load large demo dataset (facilities, practitioners, staff, documents, applications)"

    def handle(self, *args, **options):
        today = timezone.now().date()
        password = "demo1234"
        demo_pdf = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
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
        for idx, p in enumerate(practitioners[1:16], start=2):
            if User.objects.filter(practitioner_profile=p).exists():
                continue
            User.objects.create_user(
                username=f"doctor_{idx:02d}",
                password=password,
                role=User.Role.PRACTITIONER,
                practitioner_profile=p,
                email=f"doctor_{idx:02d}@demo.nmalis.ke",
            )
        main_facility = facilities[0]
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
                    doc.file.save(f"{ref}.pdf", ContentFile(demo_pdf), save=True)

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
                doc.file.save(f"{ref}.pdf", ContentFile(demo_pdf), save=True)

        regulator, created = User.objects.update_or_create(
            username="regulator",
            defaults={"role": User.Role.REGULATOR, "email": "regulator@kmpdc.demo.ke", "is_staff": True},
        )
        if created:
            regulator.set_password(password)
            regulator.save()

        hospital_admin, created = User.objects.update_or_create(
            username="hospital_admin",
            defaults={
                "role": User.Role.HOSPITAL_ADMIN,
                "facility": main_facility,
                "email": "admin@test-hospital.demo.ke",
                "personal_physician": sample_main,
            },
        )
        if created:
            hospital_admin.set_password(password)
            hospital_admin.save()
        else:
            hospital_admin.facility = main_facility
            hospital_admin.personal_physician = sample_main
            hospital_admin.save(update_fields=["facility", "personal_physician"])

        existing_holder = User.objects.filter(practitioner_profile=sample_main).first()
        if existing_holder and existing_holder.username != "doctor_sample":
            existing_holder.practitioner_profile = None
            existing_holder.save(update_fields=["practitioner_profile"])
        doc_sample, created = User.objects.get_or_create(
            username="doctor_sample",
            defaults={
                "role": User.Role.PRACTITIONER,
                "practitioner_profile": sample_main,
                "email": "doctor_sample@demo.nmalis.ke",
            },
        )
        if created:
            doc_sample.set_password(password)
            doc_sample.save()
        elif doc_sample.practitioner_profile_id != sample_main.pk:
            doc_sample.practitioner_profile = sample_main
            doc_sample.save(update_fields=["practitioner_profile"])

        for i in range(1, 6):
            admin, created = User.objects.update_or_create(
                username=f"hospital_admin_{i}",
                defaults={
                    "role": User.Role.HOSPITAL_ADMIN,
                    "facility": facilities[i],
                    "email": f"hospital_admin_{i}@demo.nmalis.ke",
                    "personal_physician": practitioners[i * 3],
                },
            )
            if created:
                admin.set_password(password)
                admin.save()

        for i in range(3):
            FacilityApplication.objects.get_or_create(
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

        self.stdout.write(self.style.SUCCESS("Large demo dataset loaded."))
        self.stdout.write(f"Facilities: {len(facilities)} | Practitioners: {len(practitioners)}")
        self.stdout.write("Login: regulator / hospital_admin / doctor_sample / doctor_01 … doctor_15")
        self.stdout.write(f"Password: {password}")
