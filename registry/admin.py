from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .forms import NMALISUserCreationForm
from .models import (
    ComplianceAlert,
    FacilityApplication,
    HealthcareFacility,
    PractitionerProfile,
    RegistryDocument,
    StaffAffiliation,
    StatusChangeLog,
    User,
    VerificationCheck,
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = NMALISUserCreationForm
    list_display = ("username", "email", "role", "facility", "is_staff")
    list_filter = ("role", "is_staff")
    fieldsets = BaseUserAdmin.fieldsets + (
        ("NMALIS", {"fields": ("role", "facility", "practitioner_profile", "personal_physician")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("username", "password1", "password2", "role", "email")}),
    )


@admin.register(HealthcareFacility)
class HealthcareFacilityAdmin(admin.ModelAdmin):
    list_display = ("registration_number", "name", "county", "status", "accreditation_expiry")
    list_filter = ("status", "county")
    search_fields = ("registration_number", "name")


@admin.register(PractitionerProfile)
class PractitionerProfileAdmin(admin.ModelAdmin):
    list_display = ("license_number", "full_name", "specialty", "status", "license_expiry", "cpd_points")
    list_filter = ("status", "specialty")
    search_fields = ("license_number", "full_name")


@admin.register(StaffAffiliation)
class StaffAffiliationAdmin(admin.ModelAdmin):
    list_display = ("practitioner", "facility", "role_at_facility", "is_active", "start_date")
    list_filter = ("is_active",)


@admin.register(StatusChangeLog)
class StatusChangeLogAdmin(admin.ModelAdmin):
    list_display = ("entity_label", "old_status", "new_status", "changed_by", "created_at")
    readonly_fields = ("entity_type", "entity_id", "entity_label", "old_status", "new_status", "reason", "changed_by", "created_at")


@admin.register(VerificationCheck)
class VerificationCheckAdmin(admin.ModelAdmin):
    list_display = ("check_type", "query_identifier", "result_status", "performed_by", "created_at")
    list_filter = ("check_type", "result_status")


@admin.register(ComplianceAlert)
class ComplianceAlertAdmin(admin.ModelAdmin):
    list_display = ("title", "alert_type", "recipient", "is_read", "created_at")
    list_filter = ("alert_type", "is_read")


@admin.register(FacilityApplication)
class FacilityApplicationAdmin(admin.ModelAdmin):
    list_display = ("facility_legal_name", "application_type", "status", "facility", "created_at")
    list_filter = ("application_type", "status")


@admin.register(RegistryDocument)
class RegistryDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "document_type", "review_status", "subject_label", "submitted_at")
    list_filter = ("document_type", "review_status")
    search_fields = ("title", "reference_number")
