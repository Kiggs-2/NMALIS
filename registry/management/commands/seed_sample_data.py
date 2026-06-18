"""Seed 7 sample records for each entity in the NMALIS system."""

from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone

from registry.models import (
    ComplianceAlert,
    FacilityApplication,
    HealthcareFacility,
    LicenseStatus,
    PractitionerProfile,
    PractitionerRenewalApplication,
    RegistryDocument,
    StaffAffiliation,
    StatusChangeLog,
    User,
    VerificationCheck,
)
from sysadmin.models import SupportTicket


class Command(BaseCommand):
    help = "Seed 7 sample records for every entity in the NMALIS system"

    def handle(self, *args, **options):
        today = timezone.now().date()
        password = "demo1234"
        demo_pdf = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
        media_root = Path(settings.MEDIA_ROOT)
        media_root.mkdir(parents=True, exist_ok=True)

        # ── 1. HealthcareFacility (7) ─────────────────────────────────────────
        facilities = []
        facility_data = [
            ("FAC-SMP-001", "Nairobi Premier Hospital", "Nairobi", "General Medicine, Surgery, Maternity"),
            ("FAC-SMP-002", "Coast General Teaching Hospital", "Mombasa", "Paediatrics, Emergency, Laboratory"),
            ("FAC-SMP-003", "Rift Valley Medical Centre", "Nakuru", "Radiology, Orthopaedics, Pharmacy"),
            ("FAC-SMP-004", "Western Provincial Hospital", "Kakamega", "General Medicine, Surgery, ICU"),
            ("FAC-SMP-005", "Lake Basin Health Complex", "Kisumu", "Maternity, Immunization, Outpatient"),
            ("FAC-SMP-006", "Mount Kenya Clinic", "Nyeri", "General Practice, Dentistry, Lab"),
            ("FAC-SMP-007", "North Eastern Field Hospital", "Garissa", "Emergency, Nutrition, General Medicine"),
        ]
        status_cycle = [LicenseStatus.ACTIVE, LicenseStatus.ACTIVE, LicenseStatus.ACTIVE,
                        LicenseStatus.PENDING_RENEWAL, LicenseStatus.ACTIVE,
                        LicenseStatus.ACTIVE, LicenseStatus.SUSPENDED]
        for i, (reg, name, county, services) in enumerate(facility_data):
            fac, _ = HealthcareFacility.objects.update_or_create(
                registration_number=reg,
                defaults={
                    "name": name,
                    "county": county,
                    "services_offered": services,
                    "status": status_cycle[i],
                    "accreditation_expiry": today + timedelta(days=365 - i * 40),
                },
            )
            facilities.append(fac)

        # ── 2. PractitionerProfile (7) ────────────────────────────────────────
        practitioner_data = [
            ("KMP-SMP-001", "Dr. James Kiprop", "General Practice", LicenseStatus.ACTIVE, 200, 180, 65),
            ("KMP-SMP-002", "Dr. Grace Akinyi", "Paediatrics", LicenseStatus.ACTIVE, 280, 250, 55),
            ("KMP-SMP-003", "Dr. Peter Kamau", "Surgery", LicenseStatus.PENDING_RENEWAL, 60, 90, 38),
            ("KMP-SMP-004", "Dr. Esther Wambui", "Obstetrics", LicenseStatus.ACTIVE, 350, 320, 72),
            ("KMP-SMP-005", "Dr. David Odhiambo", "Radiology", LicenseStatus.SUSPENDED, 100, 45, 60),
            ("KMP-SMP-006", "Dr. Susan Njoki", "Internal Medicine", LicenseStatus.EXPIRED, 10, 30, 45),
            ("KMP-SMP-007", "Dr. Brian Mutua", "Anaesthesia", LicenseStatus.ACTIVE, 180, 200, 80),
        ]
        practitioners = []
        for lic, name, spec, status, lic_exp, ind_exp, cpd in practitioner_data:
            p, _ = PractitionerProfile.objects.update_or_create(
                license_number=lic,
                defaults={
                    "full_name": name,
                    "specialty": spec,
                    "status": status,
                    "license_expiry": today + timedelta(days=lic_exp),
                    "indemnity_expiry": today + timedelta(days=ind_exp),
                    "cpd_points": cpd,
                },
            )
            practitioners.append(p)

        # ── 3. User (7) — one of each role + extras ────────────────────────────
        user_data = [
            ("regulator_smp", User.Role.REGULATOR, None, None, "regulator_smp@nmalis.ke"),
            ("hospital_admin_smp", User.Role.HOSPITAL_ADMIN, facilities[0], None, "admin_smp@nmalis.ke"),
            ("practitioner_smp_1", User.Role.PRACTITIONER, None, practitioners[0], "jkiprop@nmalis.ke"),
            ("practitioner_smp_2", User.Role.PRACTITIONER, None, practitioners[1], "gakinyi@nmalis.ke"),
            ("practitioner_smp_3", User.Role.PRACTITIONER, None, practitioners[2], "pkamau@nmalis.ke"),
            ("sysadmin_smp", User.Role.SYSTEM_ADMIN, None, None, "sysadmin_smp@nmalis.ke"),
            ("practitioner_smp_4", User.Role.PRACTITIONER, None, practitioners[3], "ewambui@nmalis.ke"),
        ]
        users = []
        for uname, role, facility, profile, email in user_data:
            u, created = User.objects.update_or_create(
                username=uname,
                defaults={
                    "role": role,
                    "facility": facility,
                    "practitioner_profile": profile,
                    "email": email,
                },
            )
            if created:
                u.set_password(password)
                u.save()
            # Link personal_physician for hospital_admin
            if role == User.Role.HOSPITAL_ADMIN and profile is None:
                u.personal_physician = practitioners[0]
                u.save(update_fields=["personal_physician"])
            users.append(u)

        # ── 4. StaffAffiliation (7) ────────────────────────────────────────────
        affiliation_data = [
            (practitioners[0], facilities[0], "Consultant Physician"),
            (practitioners[1], facilities[0], "Paediatrician"),
            (practitioners[2], facilities[1], "Visiting Surgeon"),
            (practitioners[3], facilities[2], "Lead Obstetrician"),
            (practitioners[4], facilities[3], "Radiologist"),
            (practitioners[5], facilities[5], "Physician"),
            (practitioners[6], facilities[4], "Anaesthesiologist"),
        ]
        for p, fac, role in affiliation_data:
            StaffAffiliation.objects.update_or_create(
                practitioner=p,
                facility=fac,
                defaults={"role_at_facility": role, "is_active": True},
            )

        # ── 5. RegistryDocument (7) ────────────────────────────────────────────
        doc_data = [
            (practitioners[0], None, RegistryDocument.DocumentType.PRACTITIONER_LICENSE,
             "Annual Practising Licence 2025", f"{practitioners[0].license_number}-LIC",
             RegistryDocument.ReviewStatus.VERIFIED, practitioners[0].license_expiry),
            (practitioners[0], None, RegistryDocument.DocumentType.PROFESSIONAL_INDEMNITY,
             "Professional Indemnity Cover", f"IND-{practitioners[0].license_number}",
             RegistryDocument.ReviewStatus.VERIFIED, practitioners[0].indemnity_expiry),
            (practitioners[1], None, RegistryDocument.DocumentType.CPD_CERTIFICATE,
             "CPD Certificate — 40 Points", f"CPD-{practitioners[1].license_number}",
             RegistryDocument.ReviewStatus.VERIFIED, today + timedelta(days=365)),
            (practitioners[2], None, RegistryDocument.DocumentType.PRACTITIONER_LICENSE,
             "Practising Licence (pending review)", practitioners[2].license_number,
             RegistryDocument.ReviewStatus.PENDING, practitioners[2].license_expiry),
            (None, facilities[0], RegistryDocument.DocumentType.FACILITY_ACCREDITATION,
             "Level 5 Accreditation Certificate", f"{facilities[0].registration_number}-ACC",
             RegistryDocument.ReviewStatus.VERIFIED, facilities[0].accreditation_expiry),
            (None, facilities[3], RegistryDocument.DocumentType.FACILITY_ACCREDITATION,
             "Accreditation (expired)", facilities[3].registration_number,
             RegistryDocument.ReviewStatus.REJECTED, facilities[3].accreditation_expiry),
            (practitioners[4], None, RegistryDocument.DocumentType.INTERNSHIP_CERTIFICATE,
             "Internship Completion", f"INT-{practitioners[4].license_number}",
             RegistryDocument.ReviewStatus.VERIFIED, None),
        ]
        for prac, fac, doc_type, title, ref, review, expires in doc_data:
            doc, _ = RegistryDocument.objects.update_or_create(
                reference_number=ref,
                defaults={
                    "practitioner": prac,
                    "facility": fac,
                    "document_type": doc_type,
                    "title": title,
                    "review_status": review,
                    "expires_on": expires,
                },
            )
            if not doc.file:
                doc.file.save(f"{ref}.pdf", ContentFile(demo_pdf), save=True)

        # ── 6. StatusChangeLog (7) ─────────────────────────────────────────────
        regulator_user = users[0]  # regulator_smp
        status_changes = [
            (practitioners[0], "practitioner", LicenseStatus.PENDING_RENEWAL,
             LicenseStatus.ACTIVE, "Compliance check passed — all docs verified."),
            (practitioners[2], "practitioner", LicenseStatus.ACTIVE,
             LicenseStatus.PENDING_RENEWAL, "CPD points below threshold (38/50)."),
            (practitioners[4], "practitioner", LicenseStatus.ACTIVE,
             LicenseStatus.SUSPENDED, "Indemnity certificate expired and not renewed."),
            (practitioners[5], "practitioner", LicenseStatus.ACTIVE,
             LicenseStatus.EXPIRED, "License expiry date passed."),
            (facilities[3], "facility", LicenseStatus.ACTIVE,
             LicenseStatus.PENDING_RENEWAL, "Accreditation renewal due."),
            (facilities[6], "facility", LicenseStatus.ACTIVE,
             LicenseStatus.SUSPENDED, "Failed inspection — standards not met."),
            (facilities[1], "facility", LicenseStatus.ACTIVE,
             LicenseStatus.ACTIVE, "Routine compliance audit — passed."),
        ]
        for entity, etype, old, new, reason in status_changes:
            StatusChangeLog.objects.get_or_create(
                entity_type=etype,
                entity_id=entity.pk,
                entity_label=str(entity),
                new_status=new,
                defaults={
                    "old_status": old,
                    "reason": reason,
                    "changed_by": regulator_user,
                    "created_at": today - timedelta(days=5),
                },
            )

        # ── 7. VerificationCheck (7) ────────────────────────────────────────────
        check_data = [
            (VerificationCheck.CheckType.DOCTOR_BY_ADMIN, users[1], practitioners[0].license_number,
             "active", "Dr. James Kiprop — ACTIVE, licence valid until " + str(practitioners[0].license_expiry)),
            (VerificationCheck.CheckType.DOCTOR_BY_ADMIN, users[1], practitioners[1].license_number,
             "active", "Dr. Grace Akinyi — ACTIVE, all documents verified."),
            (VerificationCheck.CheckType.DOCTOR_BY_ADMIN, users[1], practitioners[2].license_number,
             "pending_renewal", "Dr. Peter Kamau — PENDING RENEWAL, CPD insufficient."),
            (VerificationCheck.CheckType.DOCTOR_BY_ADMIN, users[1], practitioners[4].license_number,
             "suspended", "Dr. David Odhiambo — SUSPENDED, indemnity expired."),
            (VerificationCheck.CheckType.FACILITY_BY_DOCTOR, users[4], facilities[0].registration_number,
             "active", "Nairobi Premier Hospital — ACTIVE, accredited until " + str(facilities[0].accreditation_expiry)),
            (VerificationCheck.CheckType.FACILITY_BY_DOCTOR, users[4], facilities[3].registration_number,
             "pending_renewal", "Western Provincial Hospital — accreditation renewal pending."),
            (VerificationCheck.CheckType.FACILITY_BY_DOCTOR, users[4], facilities[6].registration_number,
             "suspended", "North Eastern Field Hospital — SUSPENDED, failed inspection."),
        ]
        for ctype, performer, identifier, result, summary in check_data:
            VerificationCheck.objects.update_or_create(
                check_type=ctype,
                performed_by=performer,
                query_identifier=identifier,
                defaults={
                    "result_status": result,
                    "result_summary": summary,
                },
            )

        # ── 8. FacilityApplication (7) ─────────────────────────────────────────
        app_data = [
            (facilities[2], FacilityApplication.ApplicationType.SERVICES_UPDATE,
             "Rift Valley Medical Centre", "FAC-SMP-003", "Nakuru",
             "Rift Valley Medical Centre, Nakuru CBD", "P.O. Box 123-20100",
             "+254722100001", "rvmc@nmalis.ke", "Dr. Samuel Rono",
             120, "ICU, Dialysis, Oncology", today + timedelta(days=365)),
            (facilities[4], FacilityApplication.ApplicationType.LICENCE_RENEWAL,
             "Lake Basin Health Complex", "FAC-SMP-005", "Kisumu",
             "Lake Basin Road, Kisumu", "P.O. Box 456-40100",
             "+254733200002", "lbhc@nmalis.ke", "Dr. Rose Achieng",
             80, "General Medicine, Surgery, Maternity", today + timedelta(days=365)),
            (facilities[5], FacilityApplication.ApplicationType.SERVICES_UPDATE,
             "Mount Kenya Clinic", "FAC-SMP-006", "Nyeri",
             "Mount Kenya Road, Nyeri Town", "P.O. Box 789-10100",
             "+254711300003", "mkc@nmalis.ke", "Dr. Patrick Gichuki",
             30, "Dental Surgery, Radiology", today + timedelta(days=180)),
            (facilities[1], FacilityApplication.ApplicationType.LICENCE_RENEWAL,
             "Coast General Teaching Hospital", "FAC-SMP-002", "Mombasa",
             "Mombasa-Malindi Road", "P.O. Box 321-80100",
             "+254741400004", "cgh@nmalis.ke", "Dr. Fatima Hassan",
             250, "All services as per Level 6 hospital", today + timedelta(days=365)),
            (facilities[0], FacilityApplication.ApplicationType.SERVICES_UPDATE,
             "Nairobi Premier Hospital", "FAC-SMP-001", "Nairobi",
             "Upper Hill Medical District", "P.O. Box 100-00100",
             "+254720500005", "nph@nmalis.ke", "Dr. John Mwangi",
             200, "Cardiology, Neurosurgery, Transplant", today + timedelta(days=730)),
            (facilities[3], FacilityApplication.ApplicationType.LICENCE_RENEWAL,
             "Western Provincial Hospital", "FAC-SMP-004", "Kakamega",
             "Kakamega – Webuye Road", "P.O. Box 567-50100",
             "+254712600006", "wph@nmalis.ke", "Dr. Anne Okoth",
             100, "General Medicine, Surgery, Pediatrics", today + timedelta(days=365)),
            (facilities[6], FacilityApplication.ApplicationType.LICENCE_RENEWAL,
             "North Eastern Field Hospital", "FAC-SMP-007", "Garissa",
             "Garissa Town Centre", "P.O. Box 890-70100",
             "+254721700007", "nefh@nmalis.ke", "Dr. Hassan Noor",
             50, "Emergency, Nutrition, General Medicine", today + timedelta(days=180)),
        ]
        statuses = [
            FacilityApplication.ApplicationStatus.APPROVED,
            FacilityApplication.ApplicationStatus.PENDING,
            FacilityApplication.ApplicationStatus.APPROVED,
            FacilityApplication.ApplicationStatus.PENDING,
            FacilityApplication.ApplicationStatus.PENDING,
            FacilityApplication.ApplicationStatus.REJECTED,
            FacilityApplication.ApplicationStatus.PENDING,
        ]
        for i, (fac, atype, legal, reg, county, phys, postal, tel, email, director,
                 beds, services, sought) in enumerate(app_data):
            FacilityApplication.objects.update_or_create(
                facility=fac,
                application_type=atype,
                defaults={
                    "status": statuses[i],
                    "submitted_by": users[1],
                    "facility_legal_name": legal,
                    "registration_number": reg,
                    "county": county,
                    "physical_address": phys,
                    "postal_address": postal,
                    "telephone": tel,
                    "email": email,
                    "director_name": director,
                    "bed_capacity": beds,
                    "services_requested": services,
                    "accreditation_sought_until": sought,
                    "declaration_agreed": True,
                },
            )

        # ── 9. PractitionerRenewalApplication (7) ──────────────────────────────
        renewal_data = [
            (practitioners[0], "Nairobi Premier Hospital", "+254722111001",
             "jkiprop@nph.ke", "Yes", "", "No", ""),
            (practitioners[1], "Nairobi Premier Hospital", "+254733111002",
             "gakinyi@nph.ke", "Yes", "", "No", ""),
            (practitioners[2], "Coast General Hospital", "+254711111003",
             "pkamau@cgh.ke", "No", "One-year sabbatical for research", "No", ""),
            (practitioners[3], "Rift Valley Medical Centre", "+254744111004",
             "ewambui@rvmc.ke", "Yes", "", "No", ""),
            (practitioners[4], "Western Provincial Hospital", "+254722111005",
             "dodhiambo@wph.ke", "Yes", "", "Yes", "Malpractice suit ongoing — under investigation"),
            (practitioners[6], "Lake Basin Health Complex", "+254733111006",
             "bmutua@lbhc.ke", "Yes", "", "No", ""),
            (practitioners[5], "Mount Kenya Clinic", "+254711111007",
             "snjoki@mkc.ke", "No", "Maternity leave (6 months)", "No", ""),
        ]
        for p, employer, phone, email, continuous, break_reason, malpractice, malpractice_details in renewal_data:
            PractitionerRenewalApplication.objects.update_or_create(
                practitioner=p,
                defaults={
                    "current_employer": employer,
                    "work_contact_phone": phone,
                    "work_email": email,
                    "has_practised_continuously": continuous,
                    "practice_break_reason": break_reason,
                    "has_malpractice_history": malpractice,
                    "malpractice_details": malpractice_details,
                },
            )

        # ── 10. ComplianceAlert (7) ────────────────────────────────────────────
        alert_data = [
            (ComplianceAlert.AlertType.LICENSE_EXPIRING, users[1],
             "License expiring soon — Dr. Peter Kamau",
             f"Practitioner license for Dr. Peter Kamau expires in 60 days (due {practitioners[2].license_expiry}).",
             practitioners[2], None),
            (ComplianceAlert.AlertType.STAFF_NON_COMPLIANT, users[1],
             "Non-compliant staff detected",
             f"Dr. David Odhiambo (SUSPENDED) is listed as staff at Western Provincial Hospital.",
             practitioners[4], facilities[3]),
            (ComplianceAlert.AlertType.ACCREDITATION_EXPIRING, users[1],
             "Facility accreditation expiring — Western Provincial Hospital",
             f"Accreditation expires on {facilities[3].accreditation_expiry}. Please initiate renewal.",
             None, facilities[3]),
            (ComplianceAlert.AlertType.STATUS_CHANGED, users[2],
             "Your license status has changed",
             "Your CPD points are below the renewal threshold. Please complete CPD to restore active status.",
             practitioners[2], None),
            (ComplianceAlert.AlertType.STATUS_CHANGED, users[4],
             "Your license has been suspended",
             "Your Professional Indemnity certificate expired. Immediate action required.",
             practitioners[4], None),
            (ComplianceAlert.AlertType.LICENSE_EXPIRING, users[6],
             "License renewal reminder",
             f"Your license expires on {practitioners[3].license_expiry}. Submit renewal application.",
             practitioners[3], None),
            (ComplianceAlert.AlertType.ACCREDITATION_EXPIRING, users[0],
             "Multiple facilities approaching expiry",
             "Three facilities have accreditation expiring within 90 days. Review and send reminders.",
             None, None),
        ]
        for atype, recipient, title, msg, prac, fac in alert_data:
            ComplianceAlert.objects.update_or_create(
                alert_type=atype,
                recipient=recipient,
                title=title,
                defaults={
                    "message": msg,
                    "related_practitioner": prac,
                    "related_facility": fac,
                },
            )

        # ── 11. SupportTicket (7) ──────────────────────────────────────────────
        ticket_data = [
            ("Unable to verify practitioner license", SupportTicket.Priority.HIGH,
             "The verification tool returns an error when checking KMP-SMP-005. Please investigate.",
             users[1], SupportTicket.Status.IN_PROGRESS),
            ("Add new facility to registry", SupportTicket.Priority.MEDIUM,
             "We have acquired a new clinic in Kisii and need it added to the NMALIS system.",
             users[1], SupportTicket.Status.OPEN),
            ("User account locked after 3 attempts", SupportTicket.Priority.HIGH,
             "Practitioner Dr. Esther Wambui cannot log in. Account locked after failed attempts.",
             users[3], SupportTicket.Status.OPEN),
            ("System slow during peak hours", SupportTicket.Priority.LOW,
             "Response times are very slow between 9 AM and 11 AM. Possible server load issue.",
             users[0], SupportTicket.Status.RESOLVED),
            ("Password reset not sending email", SupportTicket.Priority.MEDIUM,
             "Practitioner reports no email received after requesting password reset. Check SMTP config.",
             users[2], SupportTicket.Status.IN_PROGRESS),
            ("Data export feature request", SupportTicket.Priority.LOW,
             "Hospital admin requests ability to export staff list as CSV/Excel.",
             users[1], SupportTicket.Status.OPEN),
            ("Report: document upload fails for large PDFs", SupportTicket.Priority.MEDIUM,
             "Files over 5 MB fail to upload. Consider increasing file size limit in settings.",
             users[5], SupportTicket.Status.OPEN),
        ]
        for subject, priority, desc, submitter, status in ticket_data:
            SupportTicket.objects.update_or_create(
                subject=subject,
                submitted_by=submitter,
                defaults={
                    "description": desc,
                    "priority": priority,
                    "status": status,
                    "assigned_to": users[5],  # sysadmin_smp
                    "admin_notes": "" if status == SupportTicket.Status.OPEN else
                                  "Investigated — root cause identified, fix in progress.",
                },
            )

        self.stdout.write(self.style.SUCCESS("✓ Sample data seeded: 7 records per entity"))
        self.stdout.write("")
        self.stdout.write("Entities created:")
        self.stdout.write(f"  1. HealthcareFacility          — {HealthcareFacility.objects.count()} records")
        self.stdout.write(f"  2. PractitionerProfile         — {PractitionerProfile.objects.count()} records")
        self.stdout.write(f"  3. User                        — {User.objects.count()} records")
        self.stdout.write(f"  4. StaffAffiliation            — {StaffAffiliation.objects.count()} records")
        self.stdout.write(f"  5. RegistryDocument            — {RegistryDocument.objects.count()} records")
        self.stdout.write(f"  6. StatusChangeLog             — {StatusChangeLog.objects.count()} records")
        self.stdout.write(f"  7. VerificationCheck           — {VerificationCheck.objects.count()} records")
        self.stdout.write(f"  8. FacilityApplication         — {FacilityApplication.objects.count()} records")
        self.stdout.write(f"  9. PractitionerRenewalApplication — {PractitionerRenewalApplication.objects.count()} records")
        self.stdout.write(f" 10. ComplianceAlert             — {ComplianceAlert.objects.count()} records")
        self.stdout.write(f" 11. SupportTicket               — {SupportTicket.objects.count()} records")
        self.stdout.write("")
        self.stdout.write(f"Default password for all users: {password}")
