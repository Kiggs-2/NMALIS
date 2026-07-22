from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import FacilityApplication, HealthcareFacility, RegistryDocument, User

KMPDC_FORM_WIDGETS = {
    "facility_legal_name": forms.TextInput(attrs={"class": "form-control"}),
    "registration_number": forms.TextInput(attrs={"class": "form-control"}),
    "county": forms.TextInput(attrs={"class": "form-control"}),
    "physical_address": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
    "postal_address": forms.TextInput(attrs={"class": "form-control"}),
    "telephone": forms.TextInput(attrs={"class": "form-control"}),
    "email": forms.EmailInput(attrs={"class": "form-control"}),
    "director_name": forms.TextInput(attrs={"class": "form-control"}),
    "bed_capacity": forms.NumberInput(attrs={"class": "form-control"}),
    "services_requested": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    "supporting_file": forms.FileInput(attrs={"class": "form-control"}),
    "declaration_agreed": forms.CheckboxInput(attrs={"class": "form-check-input"}),
}


class FacilityLicenceApplicationForm(forms.ModelForm):
    class Meta:
        model = FacilityApplication
        fields = [
            "facility_legal_name", "registration_number", "county", "physical_address",
            "postal_address", "telephone", "email", "director_name", "bed_capacity",
            "services_requested", "supporting_file", "declaration_agreed",
        ]
        widgets = KMPDC_FORM_WIDGETS
        labels = {
            "facility_legal_name": "Registered name of health institution",
            "registration_number": "KMPDC facility registration number",
            "director_name": "Name of director of medical services",
            "services_requested": "Clinical services to be provided",
            "declaration_agreed": "I declare that the information provided is true and complete per KMPDC regulations.",
        }

    def clean_declaration_agreed(self):
        if not self.cleaned_data.get("declaration_agreed"):
            raise forms.ValidationError("You must accept the declaration to submit.")
        return True


class FacilityServicesUpdateForm(forms.ModelForm):
    class Meta:
        model = FacilityApplication
        fields = [
            "facility_legal_name", "registration_number", "county", "physical_address",
            "postal_address", "telephone", "email", "director_name", "bed_capacity",
            "services_requested", "supporting_file", "declaration_agreed",
        ]
        widgets = KMPDC_FORM_WIDGETS
        labels = {
            "facility_legal_name": "Registered name of health institution",
            "services_requested": "Proposed updated list of services",
            "declaration_agreed": "I declare that supporting documents are authentic and services listed are accurate.",
        }

    def clean_declaration_agreed(self):
        if not self.cleaned_data.get("declaration_agreed"):
            raise forms.ValidationError("You must accept the declaration to submit.")
        return True


ACCOUNTABILITY_STATEMENT = (
    "I confirm that I have reviewed the supporting records and accept personal "
    "accountability for this regulatory action under KMPDC procedures."
)


class FacilityApplicationReviewForm(forms.Form):
    decision = forms.ChoiceField(
        label="Decision",
        choices=[("approved", "Approve"), ("rejected", "Reject")],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    review_notes = forms.CharField(
        label="Review notes", required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )
    accountability_acknowledged = forms.BooleanField(
        label=ACCOUNTABILITY_STATEMENT, required=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

ACCOUNTABILITY_STATEMENT = (
    "I confirm that I have reviewed the supporting records and accept personal "
    "accountability for this regulatory action under KMPDC procedures."
)


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Username", "autocomplete": "username"}),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "Password", "autocomplete": "current-password"}
        ),
    )


class CredibilityCheckForm(forms.Form):
    identifier = forms.CharField(
        label="License or registration number", max_length=64,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "e.g. KMP-2024-001 or FAC-KEN-001", "autocomplete": "off"}
        ),
    )


class DocumentReviewForm(forms.Form):
    review_status = forms.ChoiceField(
        label="Review decision",
        choices=[
            ("verified", "Verified — document is authentic and acceptable"),
            ("rejected", "Rejected — document is invalid or incomplete"),
        ],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    review_notes = forms.CharField(
        label="Review notes", required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )
    accountability_acknowledged = forms.BooleanField(
        label=ACCOUNTABILITY_STATEMENT, required=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )


class FacilityRenewalForm(forms.ModelForm):
    class Meta:
        model = HealthcareFacility
        fields = ["services_offered"]
        labels = {"services_offered": "Services offered (comma-separated)"}
        widgets = {
            "services_offered": forms.Textarea(
                attrs={"class": "form-control", "rows": 4, "placeholder": "General Medicine, Surgery, Maternity"}
            )
        }


class PractitionerLicenceRenewalForm(forms.Form):
    """Practitioner licence renewal with renewal form data and document upload."""
    # Renewal form fields
    current_employer = forms.CharField(
        label="Current employer / practice name",
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Kenyatta National Hospital"}),
    )
    work_contact_phone = forms.CharField(
        label="Work contact phone",
        required=False,
        max_length=32,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. 0712 345 678"}),
    )
    work_email = forms.EmailField(
        label="Work email address",
        required=False,
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "you@practice.co.ke"}),
    )
    has_practised_continuously = forms.ChoiceField(
        label="Have you practised continuously since last renewal?",
        choices=[("", "Select…"), ("yes", "Yes — I have been in continuous practice"), ("no", "No — I took a break")],
        required=True,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    practice_break_reason = forms.CharField(
        label="If you took a break, provide details",
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Optional: maternity, study, career break, etc."}),
    )
    has_malpractice_history = forms.ChoiceField(
        label="Any adverse findings, disciplinary action, or malpractice claims since last renewal?",
        choices=[("", "Select…"), ("no", "No"), ("yes", "Yes — provide details below")],
        required=True,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    malpractice_details = forms.CharField(
        label="Details of disciplinary action or malpractice claims",
        required=False,
        max_length=1000,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Optional: describe any actions taken against you..."}),
    )

    # Document upload fields
    indemnity_file = forms.FileField(
        label="Upload current Professional Indemnity certificate (PDF)",
        required=False,
        widget=forms.FileInput(attrs={"class": "form-control", "accept": ".pdf,.jpg,.png"}),
    )
    cpd_certificate_file = forms.FileField(
        label="Upload latest CPD certificate (PDF)",
        required=False,
        widget=forms.FileInput(attrs={"class": "form-control", "accept": ".pdf,.jpg,.png"}),
    )
    licence_renewal_file = forms.FileField(
        label="Upload any supporting licence renewal document",
        required=False,
        widget=forms.FileInput(attrs={"class": "form-control", "accept": ".pdf,.jpg,.png"}),
    )

    # Declaration
    declaration_agreed = forms.BooleanField(
        label=(
            "I declare that the information provided and the uploaded documents "
            "are true, complete, and authentic to the best of my knowledge."
        ),
        required=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )


class NMALISUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "role", "email")
