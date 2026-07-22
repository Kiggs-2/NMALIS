from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from registry.models import (
    FacilityApplication,
    FacilityRenewalPayment,
    HealthcareFacility,
    LicenseStatus,
    PractitionerProfile,
    PractitionerRenewalApplication,
    PractitionerRenewalPayment,
    RegistryDocument,
    User,
)
from registry.services import verify_practitioner

User = get_user_model()


class NMALISTests(TestCase):
    def setUp(self):
        today = timezone.now().date()
        self.facility = HealthcareFacility.objects.create(
            registration_number="FAC-NBI-2024-001",
            name="Nairobi Medical Centre",
            county="Nairobi",
            status=LicenseStatus.ACTIVE,
            accreditation_expiry=today + timedelta(days=365),
        )
        self.practitioner = PractitionerProfile.objects.create(
            license_number="KMP-2024-1042",
            full_name="Dr. Jane Mwangi",
            specialty="General Practice",
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
        verify_practitioner("KMP-2024-1042", self.admin_user)
        self.assertEqual(self.admin_user.verification_checks.count(), 1)

    def test_verify_doctor_post_requires_login(self):
        url = reverse("verify_doctor")
        r = self.client.post(url, {"identifier": "KMP-2024-1042"})
        self.assertEqual(r.status_code, 302)

    def test_verify_doctor_flow(self):
        self.client.login(username="t_admin", password="pass12345")
        url = reverse("verify_doctor")
        r = self.client.post(url, {"identifier": " KMP-2024-1042 "})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Dr. Jane Mwangi")

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
            license_number="KMP-2024-2089",
            full_name="Dr. Samuel Kipchoge",
            license_expiry=today + timedelta(days=100),
            indemnity_expiry=today + timedelta(days=100),
            cpd_points=50,
        )
        for i in range(3):
            RegistryDocument.objects.create(
                practitioner=p,
                document_type=RegistryDocument.DocumentType.PRACTITIONER_LICENSE,
                title=f"License Doc {i+1}",
                reference_number=f"REF-{i+1}",
            )
        groups = group_documents_by_subject(RegistryDocument.objects.filter(practitioner=p))
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]["documents"]), 3)
        self.assertEqual(groups[0]["label"], str(p))


class ComplianceRefreshTests(TestCase):
    def test_refresh_only_saves_when_status_changes(self):
        today = timezone.now().date()
        p = PractitionerProfile.objects.create(
            license_number="KMP-2024-3055",
            full_name="Dr. Grace Achieng",
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
            email="reg_details@kmpdc.go.ke",
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
                registration_number="FAC-MBSA-2024-042",
                name="Mombasa Hospital Limited",
                county="Mombasa",
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
            registration_number="FAC-KSL-2024-001",
            name="Kenyatta National Hospital",
            county="Nairobi",
            status=LicenseStatus.ACTIVE,
            accreditation_expiry=today + timedelta(days=365),
        )
        self.practitioner = PractitionerProfile.objects.create(
            license_number="KMP-2024-4100",
            full_name="Dr. Peter Odanga",
            specialty="Internal Medicine",
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
            registration_number="FAC-EG-2024-017",
            name="Eldoret Regional Referral Hospital",
            county="Uasin Gishu",
            status=LicenseStatus.ACTIVE,
            accreditation_expiry=today + timedelta(days=300),
        )
        self.practitioner = PractitionerProfile.objects.create(
            license_number="KMP-2024-6210",
            full_name="Dr. Faith Chepkemoi",
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


class FacilityPaymentFlowTests(TestCase):
    def setUp(self):
        today = timezone.now().date()
        self.facility = HealthcareFacility.objects.create(
            registration_number="FAC-NBI-2024-017",
            name="Nairobi Women's Hospital",
            county="Nairobi",
            status=LicenseStatus.ACTIVE,
            accreditation_expiry=today + timedelta(days=15),
        )
        self.hospital_admin = User.objects.create_user(
            username="hosp_pay",
            password="pass12345",
            role=User.Role.HOSPITAL_ADMIN,
            facility=self.facility,
        )
        self.application_data = {
            "facility_legal_name": self.facility.name,
            "registration_number": self.facility.registration_number,
            "county": self.facility.county,
            "physical_address": f"{self.facility.name}, {self.facility.county}",
            "postal_address": "P.O. Box 30376",
            "telephone": "0202717070",
            "email": "info@nwhealth.co.ke",
            "director_name": "Dr. Michael Kamau",
            "bed_capacity": 120,
            "services_requested": "General Medicine, Surgery, Maternity, Paediatrics",
            "declaration_agreed": True,
        }

    def test_licence_renewal_requires_payment(self):
        self.client.login(username="hosp_pay", password="pass12345")
        url = reverse("hospital_apply_licence")
        r = self.client.post(url, self.application_data)
        self.assertEqual(r.status_code, 302)
        self.assertRedirects(r, reverse("facility_payment_step"))

    def test_services_update_requires_payment(self):
        self.client.login(username="hosp_pay", password="pass12345")
        url = reverse("hospital_apply_services")
        r = self.client.post(url, self.application_data)
        self.assertEqual(r.status_code, 302)
        self.assertRedirects(r, reverse("facility_payment_step"))

    def test_payment_step_creates_pending_payment(self):
        self.client.login(username="hosp_pay", password="pass12345")
        url = reverse("hospital_apply_licence")
        r = self.client.post(url, self.application_data)
        self.assertEqual(r.status_code, 302)
        payment_step_url = reverse("facility_payment_step")
        r = self.client.get(payment_step_url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Complete payment")

    def test_completed_payment_allows_application(self):
        self.client.login(username="hosp_pay", password="pass12345")
        url = reverse("hospital_apply_licence")
        r = self.client.post(url, self.application_data)
        self.assertEqual(r.status_code, 302)
        payment = FacilityRenewalPayment.objects.first()
        self.assertEqual(payment.status, FacilityRenewalPayment.Status.PENDING)
        payment.status = FacilityRenewalPayment.Status.COMPLETED
        payment.save(update_fields=["status"])
        r = self.client.get(reverse("hospital_facility_profile"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, self.facility.name, html=True)

    def test_facility_payment_step_redirects_without_pending_payment(self):
        self.client.login(username="hosp_pay", password="pass12345")
        r = self.client.get(reverse("facility_payment_step"))
        self.assertEqual(r.status_code, 302)
        self.assertRedirects(r, reverse("hospital_facility_profile"))

    def test_cancel_payment_marks_failed(self):
        self.client.login(username="hosp_pay", password="pass12345")
        r = self.client.post(reverse("hospital_apply_licence"), self.application_data)
        self.assertEqual(r.status_code, 302)
        payment = FacilityRenewalPayment.objects.first()
        r = self.client.post(reverse("facility_cancel_payment", args=[payment.pk]))
        self.assertEqual(r.status_code, 302)
        payment.refresh_from_db()
        self.assertEqual(payment.status, FacilityRenewalPayment.Status.FAILED)

    def test_mpesa_callback_marks_completed(self):
        self.client.login(username="hosp_pay", password="pass12345")
        r = self.client.post(reverse("hospital_apply_licence"), self.application_data)
        self.assertEqual(r.status_code, 302)
        payment = FacilityRenewalPayment.objects.first()
        payment.merchant_request_id = "test-merchant"
        payment.checkout_request_id = "test-checkout"
        payment.save(update_fields=["merchant_request_id", "checkout_request_id"])
        self.assertEqual(payment.status, FacilityRenewalPayment.Status.PENDING)
        callback_url = reverse("mpesa_callback")
        payload = {
            "Body": {
                "stkCallback": {
                    "MerchantRequestID": "test-merchant",
                    "CheckoutRequestID": "test-checkout",
                    "ResultCode": 0,
                    "ResultDesc": "Success",
                    "CallbackMetadata": {
                        "Item": [
                            {"Name": "MpesaReceiptNumber", "Value": "TEST123"},
                        ]
                    },
                }
            }
        }
        import json
        r = self.client.post(
            callback_url,
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, FacilityRenewalPayment.Status.COMPLETED)
        self.assertEqual(payment.mpesa_receipt_number, "TEST123")

    def test_mpesa_callback_marks_failed(self):
        self.client.login(username="hosp_pay", password="pass12345")
        r = self.client.post(reverse("hospital_apply_licence"), self.application_data)
        self.assertEqual(r.status_code, 302)
        payment = FacilityRenewalPayment.objects.first()
        payment.merchant_request_id = "test-merchant"
        payment.checkout_request_id = "test-checkout"
        payment.save(update_fields=["merchant_request_id", "checkout_request_id"])
        callback_url = reverse("mpesa_callback")
        payload = {
            "Body": {
                "stkCallback": {
                    "MerchantRequestID": "test-merchant",
                    "CheckoutRequestID": "test-checkout",
                    "ResultCode": 1,
                    "ResultDesc": "Failed",
                }
            }
        }
        import json
        r = self.client.post(
            callback_url,
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, FacilityRenewalPayment.Status.FAILED)

    def test_licence_renewal_blocked_when_more_than_one_month_to_expiry(self):
        self.facility.accreditation_expiry = timezone.now().date() + timedelta(days=60)
        self.facility.save(update_fields=["accreditation_expiry"])
        self.client.login(username="hosp_pay", password="pass12345")
        r = self.client.post(reverse("hospital_apply_licence"), self.application_data)
        self.assertEqual(r.status_code, 302)
        self.assertRedirects(r, reverse("hospital_facility_profile"))
        self.client.get(reverse("hospital_facility_profile"))
        self.assertFalse(FacilityRenewalPayment.objects.exists())

    def test_licence_renewal_allowed_within_one_month_to_expiry(self):
        self.facility.accreditation_expiry = timezone.now().date() + timedelta(days=15)
        self.facility.save(update_fields=["accreditation_expiry"])
        self.client.login(username="hosp_pay", password="pass12345")
        r = self.client.post(reverse("hospital_apply_licence"), self.application_data)
        self.assertEqual(r.status_code, 302)
        self.assertRedirects(r, reverse("facility_payment_step"))
        self.assertEqual(FacilityRenewalPayment.objects.count(), 1)

    def test_licence_renewal_allowed_after_rejected_application(self):
        self.facility.accreditation_expiry = timezone.now().date() + timedelta(days=60)
        self.facility.save(update_fields=["accreditation_expiry"])
        FacilityApplication.objects.create(
            facility=self.facility,
            application_type=FacilityApplication.ApplicationType.LICENCE_RENEWAL,
            status=FacilityApplication.ApplicationStatus.REJECTED,
            submitted_by=self.hospital_admin,
            facility_legal_name=self.facility.name,
            registration_number=self.facility.registration_number,
            county=self.facility.county,
            physical_address=f"{self.facility.name}, {self.facility.county}",
            telephone="+254700000001",
            email="admin@test-hospital.demo.ke",
            director_name="Dr. Sample Director",
            bed_capacity=50,
            services_requested=self.facility.services_offered,
            accreditation_sought_until=self.facility.accreditation_expiry,
            declaration_agreed=True,
            reviewed_by=User.objects.filter(role=User.Role.REGULATOR).first(),
            reviewed_at=timezone.now(),
        )
        self.client.login(username="hosp_pay", password="pass12345")
        r = self.client.post(reverse("hospital_apply_licence"), self.application_data)
        self.assertEqual(r.status_code, 302)
        self.assertRedirects(r, reverse("facility_payment_step"))
        self.assertEqual(FacilityRenewalPayment.objects.count(), 1)

    def test_services_update_allowed_any_time(self):
        self.facility.accreditation_expiry = timezone.now().date() + timedelta(days=365)
        self.facility.save(update_fields=["accreditation_expiry"])
        self.client.login(username="hosp_pay", password="pass12345")
        r = self.client.post(reverse("hospital_apply_services"), self.application_data)
        self.assertEqual(r.status_code, 302)
        self.assertRedirects(r, reverse("facility_payment_step"))

    def test_duplicate_licence_renewal_payment_blocked(self):
        self.client.login(username="hosp_pay", password="pass12345")
        r = self.client.post(reverse("hospital_apply_licence"), self.application_data)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(FacilityRenewalPayment.objects.count(), 1)
        r = self.client.post(reverse("hospital_apply_licence"), self.application_data)
        self.assertEqual(r.status_code, 302)
        self.assertRedirects(r, reverse("hospital_facility_profile"))
        self.assertEqual(FacilityRenewalPayment.objects.count(), 1)

    def test_duplicate_services_update_payment_blocked(self):
        self.client.login(username="hosp_pay", password="pass12345")
        r = self.client.post(reverse("hospital_apply_services"), self.application_data)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(FacilityRenewalPayment.objects.count(), 1)
        r = self.client.post(reverse("hospital_apply_services"), self.application_data)
        self.assertEqual(r.status_code, 302)
        self.assertRedirects(r, reverse("hospital_facility_profile"))
        self.assertEqual(FacilityRenewalPayment.objects.count(), 1)

    def test_pending_application_limit_blocks_new_submission(self):
        self.client.login(username="hosp_pay", password="pass12345")
        FacilityApplication.objects.create(
            facility=self.facility,
            application_type=FacilityApplication.ApplicationType.LICENCE_RENEWAL,
            status=FacilityApplication.ApplicationStatus.PENDING,
            facility_legal_name=self.facility.name,
            registration_number=self.facility.registration_number,
            county=self.facility.county,
            physical_address=f"{self.facility.name}, {self.facility.county}",
            postal_address="P.O. Box 123",
            telephone="0712345678",
            email="test@example.com",
            director_name="Dr. Director",
            bed_capacity=50,
            services_requested="General Medicine, Surgery",
            accreditation_sought_until=timezone.now().date() + timedelta(days=365),
            declaration_agreed=True,
            submitted_by=self.hospital_admin,
        )
        FacilityApplication.objects.create(
            facility=self.facility,
            application_type=FacilityApplication.ApplicationType.SERVICES_UPDATE,
            status=FacilityApplication.ApplicationStatus.PENDING,
            facility_legal_name=self.facility.name,
            registration_number=self.facility.registration_number,
            county=self.facility.county,
            physical_address=f"{self.facility.name}, {self.facility.county}",
            postal_address="P.O. Box 123",
            telephone="0712345678",
            email="test@example.com",
            director_name="Dr. Director",
            bed_capacity=50,
            services_requested="General Medicine, Surgery",
            accreditation_sought_until=timezone.now().date() + timedelta(days=365),
            declaration_agreed=True,
            submitted_by=self.hospital_admin,
        )
        self.assertEqual(FacilityApplication.objects.filter(facility=self.facility).count(), 2)
        r = self.client.post(reverse("hospital_apply_licence"), self.application_data)
        self.assertEqual(r.status_code, 302)
        self.assertRedirects(r, reverse("hospital_facility_profile"))
        self.assertEqual(FacilityApplication.objects.filter(facility=self.facility).count(), 2)

    def test_auto_cancel_stale_pending_payments(self):
        self.client.login(username="hosp_pay", password="pass12345")
        r = self.client.post(reverse("hospital_apply_licence"), self.application_data)
        self.assertEqual(r.status_code, 302)
        payment = FacilityRenewalPayment.objects.first()
        self.assertEqual(payment.status, FacilityRenewalPayment.Status.PENDING)
        payment.created_at = timezone.now() - timedelta(minutes=45)
        payment.save(update_fields=["created_at"])
        r = self.client.get(reverse("hospital_facility_profile"))
        self.assertEqual(r.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, FacilityRenewalPayment.Status.FAILED)

    def test_licence_renewal_creates_registry_document(self):
        self.client.login(username="hosp_pay", password="pass12345")
        data = dict(self.application_data)
        data["supporting_file"] = SimpleUploadedFile(
            "licence_doc.pdf",
            b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF",
            content_type="application/pdf",
        )
        r = self.client.post(reverse("hospital_apply_licence"), data)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(RegistryDocument.objects.filter(facility=self.facility).count(), 1)
        doc = RegistryDocument.objects.get(facility=self.facility)
        self.assertEqual(doc.document_type, RegistryDocument.DocumentType.FACILITY_ACCREDITATION)
        self.assertEqual(doc.review_status, RegistryDocument.ReviewStatus.PENDING)

    def test_services_update_creates_registry_document(self):
        self.client.login(username="hosp_pay", password="pass12345")
        data = dict(self.application_data)
        data["supporting_file"] = SimpleUploadedFile(
            "services_doc.pdf",
            b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF",
            content_type="application/pdf",
        )
        r = self.client.post(reverse("hospital_apply_services"), data)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(RegistryDocument.objects.filter(facility=self.facility).count(), 1)
        doc = RegistryDocument.objects.get(facility=self.facility)
        self.assertEqual(doc.document_type, RegistryDocument.DocumentType.FACILITY_ACCREDITATION)
        self.assertEqual(doc.review_status, RegistryDocument.ReviewStatus.PENDING)

    def test_regulator_sees_facility_application_document(self):
        self.client.login(username="hosp_pay", password="pass12345")
        data = dict(self.application_data)
        data["supporting_file"] = SimpleUploadedFile(
            "reg_doc.pdf",
            b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF",
            content_type="application/pdf",
        )
        self.client.post(reverse("hospital_apply_licence"), data)
        regulator = User.objects.create_user(
            username="reg_doc",
            password="pass12345",
            role=User.Role.REGULATOR,
            email="reg_doc@test.ke",
        )
        self.client.login(username="reg_doc", password="pass12345")
        r = self.client.get(reverse("regulator_documents"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, self.facility.registration_number)


class PractitionerRenewalFlowTests(TestCase):
    def setUp(self):
        today = timezone.now().date()
        self.practitioner = PractitionerProfile.objects.create(
            license_number="KMP-2024-7700",
            full_name="Dr. Grace Kipchoge",
            specialty="General Practice",
            status=LicenseStatus.ACTIVE,
            license_expiry=today + timedelta(days=15),
            indemnity_expiry=today + timedelta(days=100),
            cpd_points=40,
        )
        self.practitioner_user = User.objects.create_user(
            username="practitioner_renew",
            password="pass12345",
            role=User.Role.PRACTITIONER,
            practitioner_profile=self.practitioner,
        )
        self.renewal_data = {
            "current_employer": "Nairobi Hospital",
            "work_contact_phone": "+254700000000",
            "work_email": "grace@example.com",
            "has_practised_continuously": "yes",
            "practice_break_reason": "",
            "has_malpractice_history": "no",
            "malpractice_details": "",
            "indemnity_file": SimpleUploadedFile(
                "indemnity.pdf",
                b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF",
                content_type="application/pdf",
            ),
            "cpd_certificate_file": SimpleUploadedFile(
                "cpd.pdf",
                b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF",
                content_type="application/pdf",
            ),
            "licence_renewal_file": SimpleUploadedFile(
                "renewal.pdf",
                b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF",
                content_type="application/pdf",
            ),
            "declaration_agreed": True,
        }

    def test_practitioner_renewal_requires_payment_last(self):
        self.client.login(username="practitioner_renew", password="pass12345")
        r = self.client.post(reverse("practitioner_renewal"), self.renewal_data)
        self.assertEqual(r.status_code, 302)
        self.assertRedirects(r, reverse("practitioner_payment_step"))
        self.assertEqual(PractitionerRenewalApplication.objects.count(), 1)
        self.assertEqual(PractitionerRenewalPayment.objects.count(), 1)

    def test_practitioner_renewal_blocked_when_more_than_one_month_to_expiry(self):
        self.practitioner.license_expiry = timezone.now().date() + timedelta(days=60)
        self.practitioner.save(update_fields=["license_expiry"])
        self.client.login(username="practitioner_renew", password="pass12345")
        r = self.client.post(reverse("practitioner_renewal"), self.renewal_data)
        self.assertEqual(r.status_code, 302)
        self.assertRedirects(r, reverse("dashboard"))
        self.assertEqual(PractitionerRenewalApplication.objects.count(), 0)
        self.assertEqual(PractitionerRenewalPayment.objects.count(), 0)

    def test_practitioner_renewal_allowed_within_one_month_to_expiry(self):
        self.practitioner.license_expiry = timezone.now().date() + timedelta(days=15)
        self.practitioner.save(update_fields=["license_expiry"])
        self.client.login(username="practitioner_renew", password="pass12345")
        r = self.client.post(reverse("practitioner_renewal"), self.renewal_data)
        self.assertEqual(r.status_code, 302)
        self.assertRedirects(r, reverse("practitioner_payment_step"))
        self.assertEqual(PractitionerRenewalApplication.objects.count(), 1)

    def test_practitioner_renewal_allowed_after_rejected_application(self):
        self.practitioner.license_expiry = timezone.now().date() + timedelta(days=60)
        self.practitioner.save(update_fields=["license_expiry"])
        PractitionerRenewalApplication.objects.create(
            practitioner=self.practitioner,
            status=PractitionerRenewalApplication.ApplicationStatus.REJECTED,
            current_employer="Previous Employer",
            work_contact_phone="+254700000000",
            work_email="old@example.com",
            has_practised_continuously="yes",
            practice_break_reason="",
            has_malpractice_history="no",
            malpractice_details="",
            reviewed_by=self.practitioner_user,
            reviewed_at=timezone.now(),
            review_notes="Incomplete CPD. Please resubmit.",
        )
        self.client.login(username="practitioner_renew", password="pass12345")
        r = self.client.post(reverse("practitioner_renewal"), self.renewal_data)
        self.assertEqual(r.status_code, 302)
        self.assertRedirects(r, reverse("practitioner_payment_step"))
        self.assertEqual(PractitionerRenewalApplication.objects.count(), 2)

    def test_practitioner_renewal_blocked_when_pending_application_exists(self):
        self.practitioner.license_expiry = timezone.now().date() + timedelta(days=15)
        self.practitioner.save(update_fields=["license_expiry"])
        PractitionerRenewalApplication.objects.create(
            practitioner=self.practitioner,
            status=PractitionerRenewalApplication.ApplicationStatus.PENDING,
            current_employer="Previous Employer",
            work_contact_phone="+254700000000",
            work_email="old@example.com",
            has_practised_continuously="yes",
            practice_break_reason="",
            has_malpractice_history="no",
            malpractice_details="",
        )
        self.client.login(username="practitioner_renew", password="pass12345")
        r = self.client.post(reverse("practitioner_renewal"), self.renewal_data)
        self.assertEqual(r.status_code, 302)
        self.assertRedirects(r, reverse("dashboard"))
        self.assertEqual(PractitionerRenewalApplication.objects.count(), 1)

    def test_practitioner_renewal_allowed_when_approved_application_exists(self):
        self.practitioner.license_expiry = timezone.now().date() + timedelta(days=15)
        self.practitioner.save(update_fields=["license_expiry"])
        PractitionerRenewalApplication.objects.create(
            practitioner=self.practitioner,
            status=PractitionerRenewalApplication.ApplicationStatus.APPROVED,
            current_employer="Previous Employer",
            work_contact_phone="+254700000000",
            work_email="old@example.com",
            has_practised_continuously="yes",
            practice_break_reason="",
            has_malpractice_history="no",
            malpractice_details="",
        )
        self.client.login(username="practitioner_renew", password="pass12345")
        r = self.client.post(reverse("practitioner_renewal"), self.renewal_data)
        self.assertEqual(r.status_code, 302)
        self.assertRedirects(r, reverse("practitioner_payment_step"))
        self.assertEqual(PractitionerRenewalApplication.objects.count(), 2)

    def test_duplicate_practitioner_renewal_payment_blocked(self):
        self.client.login(username="practitioner_renew", password="pass12345")
        r = self.client.post(reverse("practitioner_renewal"), self.renewal_data)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(PractitionerRenewalPayment.objects.count(), 1)
        r = self.client.post(reverse("practitioner_renewal"), self.renewal_data)
        self.assertEqual(r.status_code, 302)
        self.assertRedirects(r, reverse("dashboard"))
        self.assertEqual(PractitionerRenewalPayment.objects.count(), 1)
