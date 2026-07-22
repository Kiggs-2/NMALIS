"""Load exactly 15 demo users into the system across all roles."""

import datetime
from django.core.management.base import BaseCommand
from django.db import transaction

from registry.models import (
    HealthcareFacility,
    LicenseStatus,
    PractitionerProfile,
    User,
)


class Command(BaseCommand):
    help = "Seed exactly 15 demo users (1 Sysadmin, 1 Regulator, 3 Hospital Admins, 10 Doctors)"

    @transaction.atomic
    def handle(self, *args, **options):
        password = "demo1234"
        users_created = []

        # Default expiry date for demo licenses and accreditations
        default_expiry = datetime.date(2027, 12, 31)

        # --- BASE REQUISITE MODELS ---
        # Baseline facility for Hospital Admins
        main_facility, _ = HealthcareFacility.objects.update_or_create(
            registration_number="FAC-DEMO-001",
            defaults={
                "name": "Demo General Hospital",
                "county": "Nairobi",
                "services_offered": "General Medicine, Outpatient",
                "status": LicenseStatus.ACTIVE,
                "accreditation_expiry": default_expiry,  # Fix for facility constraint
            },
        )

        # --- 1. SYSTEM ADMIN (1 User) ---
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
        users_created.append(("sysadmin", "System Admin"))

        # --- 2. REGULATOR (1 User) ---
        regulator, _ = User.objects.update_or_create(
            username="regulator",
            defaults={
                "role": User.Role.REGULATOR,
                "email": "regulator@kmpdc.demo.ke",
                "first_name": "Regulator",
                "last_name": "Officer",
                "is_staff": True,
                "is_active": True,
            },
        )
        regulator.set_password(password)
        regulator.save()
        users_created.append(("regulator", "Regulator"))

        # --- 3. HOSPITAL ADMINS (3 Users) ---
        for i in range(1, 4):
            username = "hospital_admin" if i == 1 else f"hospital_admin_{i}"
            admin, _ = User.objects.update_or_create(
                username=username,
                defaults={
                    "role": User.Role.HOSPITAL_ADMIN,
                    "facility": main_facility,
                    "email": f"{username}@demo.nmalis.ke",
                    "first_name": "Hospital",
                    "last_name": f"Admin {i}",
                    "is_active": True,
                },
            )
            admin.set_password(password)
            admin.save()
            users_created.append((username, "Hospital Admin"))

        # --- 4. PRACTITIONERS / DOCTORS (10 Users) ---
        specialties = ["General Practice", "Surgery", "Paediatrics", "Internal Medicine", "Obstetrics"]

        for i in range(1, 11):
            username = "doctor_sample" if i == 1 else f"doctor_{i:02d}"

            p_profile, _ = PractitionerProfile.objects.update_or_create(
                license_number=f"KMP-DEMO-{i:03d}",
                defaults={
                    "full_name": f"Dr. Doctor User {i}",
                    "specialty": specialties[(i - 1) % len(specialties)],
                    "status": LicenseStatus.ACTIVE,
                    "license_expiry": default_expiry,
                    "indemnity_expiry": default_expiry,  # FIXED
                },
            )

            doctor, _ = User.objects.update_or_create(
                username=username,
                defaults={
                    "role": User.Role.PRACTITIONER,
                    "practitioner_profile": p_profile,
                    "email": f"{username}@demo.nmalis.ke",
                    "first_name": "Doctor",
                    "last_name": f"User {i}",
                    "is_active": True,
                },
            )
            doctor.set_password(password)
            doctor.save()
            users_created.append((username, "Practitioner"))

        # --- SUMMARY ---
        self.stdout.write(self.style.SUCCESS(f"Successfully seeded {len(users_created)} users."))
        self.stdout.write("--------------------------------------------------")
        self.stdout.write(f"Default Password for all: {password}\n")
        self.stdout.write("Created Credentials:")
        for username, role in users_created:
            self.stdout.write(f"  - {username:<18} ({role})")
        self.stdout.write("--------------------------------------------------")