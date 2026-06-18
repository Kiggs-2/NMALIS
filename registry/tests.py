from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from registry.models import HealthcareFacility, LicenseStatus, PractitionerProfile, RegistryDocument
from registry.services import verify_practitioner

User = get_user_model()


class NMALISTests(TestCase):
    def setUp(self):
        today = timezone.now().date()
        self.facility = HealthcareFacility.objects.create(
            registration_number="FAC-T-001",
            name="Test Hospital",
            county="Test",
            status=LicenseStatus.ACTIVE,
            accreditation_expiry=today + timedelta(days=365),
        )
        self.practitioner = PractitionerProfile.objects.create(
            license_number="KMP-T-001",
            full_name="Dr. Test User",
            specialty="GP",
            status=LicenseStatus.ACTIVE,
            license_expiry=today + timedelta(days=100),
            indemnity_expiry=today + timedelta(days=100),
            cpd_points=55,
        )
        self.admin_user = User.objects.create_user(
            username="t_admin",
            password="pass12345",
            role=User.Role.HOSPITAL_ADMIN,
            facility=self.facility,
        )

    def test_credibility_check_logs_and_returns_found(self):
        verify_practitioner("KMP-T-001", self.admin_user)
        self.assertEqual(self.admin_user.verification_checks.count(), 1)

    def test_verify_doctor_post_requires_login(self):
        url = reverse("verify_doctor")
        r = self.client.post(url, {"identifier": "KMP-T-001"})
        self.assertEqual(r.status_code, 302)

    def test_verify_doctor_flow(self):
        self.client.login(username="t_admin", password="pass12345")
        url = reverse("verify_doctor")
        r = self.client.post(url, {"identifier": " KMP-T-001 "})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Dr. Test User")

    def test_admin_add_user_form_has_role(self):
        superuser = User.objects.create_superuser(
            username="su",
            password="pass12345",
            email="su@test.ke",
            role=User.Role.REGULATOR,
        )
        self.client.login(username="su", password="pass12345")
        r = self.client.get(reverse("admin:registry_user_add"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "role")


class DocumentDossierTests(TestCase):
    def test_group_documents_by_practitioner(self):
        from registry.document_utils import group_documents_by_subject
        from registry.models import RegistryDocument

        today = timezone.now().date()
        p = PractitionerProfile.objects.create(
            license_number="KMP-DOS-1",
            full_name="Dr. Dossier Test",
            license_expiry=today + timedelta(days=100),
            indemnity_expiry=today + timedelta(days=100),
            cpd_points=50,
        )
        for i in range(3):
            RegistryDocument.objects.create(
                practitioner=p,
                document_type=RegistryDocument.DocumentType.PRACTITIONER_LICENSE,
                title=f"Doc {i}",
                reference_number=f"REF-{i}",
            )
        groups = group_documents_by_subject(RegistryDocument.objects.filter(practitioner=p))
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]["documents"]), 3)
        self.assertEqual(groups[0]["label"], str(p))


class ComplianceRefreshTests(TestCase):
    def test_refresh_only_saves_when_status_changes(self):
        today = timezone.now().date()
        p = PractitionerProfile.objects.create(
            license_number="KMP-T-CMP",
            full_name="Dr. CMP",
            status=LicenseStatus.ACTIVE,
            license_expiry=today + timedelta(days=10),
            indemnity_expiry=today + timedelta(days=10),
            cpd_points=55,
        )
        first_updated = p.updated_at
        changed = p.refresh_compliance_status()
        self.assertFalse(changed)
        p.refresh_from_db()
        self.assertEqual(p.updated_at, first_updated)


class RegulatorAccountViewTests(TestCase):
    def test_regulator_can_view_my_details(self):
        user = User.objects.create_user(
            username="reg_details",
            password="pass12345",
            role=User.Role.REGULATOR,
            email="reg_details@test.ke",
        )
        self.client.login(username="reg_details", password="pass12345")
        r = self.client.get(reverse("regulator_account"))
        self.assertEqual(r.status_code, 200)

    def test_non_regulator_gets_403(self):
        user = User.objects.create_user(
            username="not_reg",
            password="pass12345",
            role=User.Role.HOSPITAL_ADMIN,
            facility=HealthcareFacility.objects.create(
                registration_number="FAC-TEST-403",
                name="403 Test Hospital",
                county="Test",
                status=LicenseStatus.ACTIVE,
                accreditation_expiry=timezone.now().date() + timedelta(days=30),
            ),
            email="not_reg@test.ke",
        )
        self.client.login(username="not_reg", password="pass12345")
        r = self.client.get(reverse("regulator_account"))
        self.assertEqual(r.status_code, 403)


class CertificateTests(TestCase):
    def setUp(self):
        today = timezone.now().date()
        self.facility = HealthcareFacility.objects.create(
            registration_number="FAC-CERT-001",
            name="Cert Hospital",
            county="Nairobi",
            status=LicenseStatus.ACTIVE,
            accreditation_expiry=today + timedelta(days=365),
        )
        self.practitioner = PractitionerProfile.objects.create(
            license_number="KMP-CERT-001",
            full_name="Dr. Cert Sample",
            specialty="GP",
            status=LicenseStatus.ACTIVE,
            license_expiry=today + timedelta(days=200),
            indemnity_expiry=today + timedelta(days=200),
            cpd_points=60,
        )
        self.practitioner.user_account = User.objects.create_user(
            username="prac_cert",
            password="pass12345",
            role=User.Role.PRACTITIONER,
            practitioner_profile=self.practitioner,
        )
        self.practitioner.save()
        self.regulator = User.objects.create_user(
            username="reg_cert",
            password="pass12345",
            role=User.Role.REGULATOR,
        )
        self.hospital_admin = User.objects.create_user(
            username="hosp_cert",
            password="pass12345",
            role=User.Role.HOSPITAL_ADMIN,
            facility=self.facility,
        )

    def test_regulator_downloads_practitioner_pdf(self):
        self.client.login(username="reg_cert", password="pass12345")
        url = reverse("download_practitioner_certificate", args=[self.practitioner.pk])
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertIn("attachment", r.get("Content-Disposition", ""))

    def test_practitioner_downloads_own_pdf_when_active(self):
        self.client.login(username="prac_cert", password="pass12345")
        url = reverse("download_practitioner_certificate", args=[self.practitioner.pk])
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")

    def test_hospital_admin_downloads_facility_pdf(self):
        self.client.login(username="hosp_cert", password="pass12345")
        url = reverse("download_facility_certificate", args=[self.facility.pk])
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")


class DocumentWorkflowTests(TestCase):
    def setUp(self):
        today = timezone.now().date()
        self.regulator = User.objects.create_user(
            username="reg_workflow",
            password="pass12345",
            role=User.Role.REGULATOR,
        )
        self.facility = HealthcareFacility.objects.create(
            registration_number="FAC-WRK-001",
            name="Workflow Hospital",
            county="Nakuru",
            status=LicenseStatus.ACTIVE,
            accreditation_expiry=today + timedelta(days=300),
        )
        self.practitioner = PractitionerProfile.objects.create(
            license_number="KMP-WRK-001",
            full_name="Dr. Workflow",
            status=LicenseStatus.ACTIVE,
            license_expiry=today + timedelta(days=300),
            indemnity_expiry=today + timedelta(days=300),
            cpd_points=55,
        )
        self.prac_user = User.objects.create_user(
            username="prac_workflow",
            password="pass12345",
            role=User.Role.PRACTITIONER,
            practitioner_profile=self.practitioner,
        )
        self.admin_user = User.objects.create_user(
            username="admin_workflow",
            password="pass12345",
            role=User.Role.HOSPITAL_ADMIN,
            facility=self.facility,
        )
        self.pdf = SimpleUploadedFile(
            "doc.pdf",
            b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF",
            content_type="application/pdf",
        )

    def test_rejected_practitioner_document_suspends_practitioner(self):
        doc = RegistryDocument.objects.create(
            practitioner=self.practitioner,
            document_type=RegistryDocument.DocumentType.PRACTITIONER_LICENSE,
            title="Practitioner License",
            reference_number="WRK-PRAC-001",
            file=self.pdf,
        )
        self.client.login(username="reg_workflow", password="pass12345")
        r = self.client.post(
            reverse("regulator_document_review", args=[doc.pk]),
            {
                "review_status": RegistryDocument.ReviewStatus.REJECTED,
                "review_notes": "Forged document",
                "accountability_acknowledged": "on",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.practitioner.refresh_from_db()
        self.assertEqual(self.practitioner.status, LicenseStatus.SUSPENDED)

    def test_verified_practitioner_document_creates_notification(self):
        doc = RegistryDocument.objects.create(
            practitioner=self.practitioner,
            document_type=RegistryDocument.DocumentType.PRACTITIONER_LICENSE,
            title="Practitioner License",
            reference_number="WRK-PRAC-002",
            file=self.pdf,
        )
        self.client.login(username="reg_workflow", password="pass12345")
        self.client.post(
            reverse("regulator_document_review", args=[doc.pk]),
            {
                "review_status": RegistryDocument.ReviewStatus.VERIFIED,
                "review_notes": "Verified",
                "accountability_acknowledged": "on",
            },
        )
        self.assertTrue(
            self.prac_user.compliance_alerts.filter(title__icontains="certificate issued").exists()
        )

    def test_all_verified_docs_keep_subject_active(self):
        doc = RegistryDocument.objects.create(
            practitioner=self.practitioner,
            document_type=RegistryDocument.DocumentType.CPD_CERTIFICATE,
            title="CPD Record",
            reference_number="WRK-PRAC-004",
            file=self.pdf,
        )
        self.client.login(username="reg_workflow", password="pass12345")
        self.client.post(
            reverse("regulator_document_review", args=[doc.pk]),
            {
                "review_status": RegistryDocument.ReviewStatus.VERIFIED,
                "review_notes": "Verified CPD",
                "accountability_acknowledged": "on",
            },
        )
        self.practitioner.refresh_from_db()
        self.assertEqual(self.practitioner.status, LicenseStatus.ACTIVE)

    def test_expiry_sets_subject_status_automatically(self):
        self.practitioner.license_expiry = timezone.now().date() - timedelta(days=1)
        self.practitioner.save(update_fields=["license_expiry", "updated_at"])
        self.client.login(username="reg_workflow", password="pass12345")
        self.client.get(reverse("regulator_practitioner_detail", args=[self.practitioner.pk]))
        self.practitioner.refresh_from_db()
        self.assertEqual(self.practitioner.status, LicenseStatus.EXPIRED)

    def test_document_preview_uses_inline_disposition(self):
        doc = RegistryDocument.objects.create(
            practitioner=self.practitioner,
            document_type=RegistryDocument.DocumentType.PRACTITIONER_LICENSE,
            title="Preview License",
            reference_number="WRK-PRAC-003",
            file=self.pdf,
        )
        self.client.login(username="reg_workflow", password="pass12345")
        r = self.client.get(reverse("document_preview", args=[doc.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertIn("inline", r.get("Content-Disposition", ""))
