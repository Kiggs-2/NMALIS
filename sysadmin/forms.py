from django import forms
from django.contrib.auth.forms import UserCreationForm

from registry.models import HealthcareFacility, PractitionerProfile, User
from .models import SupportTicket


class SystemUserCreateForm(UserCreationForm):
    role = forms.ChoiceField(
        choices=User.Role.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={"class": "form-control"}),
    )
    facility = forms.ModelChoiceField(
        queryset=HealthcareFacility.objects.all(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Required for hospital administrators.",
    )
    practitioner_profile = forms.ModelChoiceField(
        queryset=PractitionerProfile.objects.all(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Required for practitioners.",
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "role", "facility", "practitioner_profile")
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].widget.attrs["class"] = "form-control"
        self.fields["password2"].widget.attrs["class"] = "form-control"


class SystemUserEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name", "role", "facility", "practitioner_profile", "is_active")
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "role": forms.Select(attrs={"class": "form-select"}),
            "facility": forms.Select(attrs={"class": "form-select"}),
            "practitioner_profile": forms.Select(attrs={"class": "form-select"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class ResetPasswordForm(forms.Form):
    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
        min_length=8,
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )

    def clean(self):
        cleaned = super().clean()
        pw1 = cleaned.get("new_password")
        pw2 = cleaned.get("confirm_password")
        if pw1 and pw2 and pw1 != pw2:
            self.add_error("confirm_password", "Passwords do not match.")
        return cleaned


class TicketResponseForm(forms.Form):
    status = forms.ChoiceField(
        choices=SupportTicket.Status.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    admin_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4,
                                      "placeholder": "Add internal notes or a response..."}),
    )


class SubmitTicketForm(forms.ModelForm):
    class Meta:
        model = SupportTicket
        fields = ("subject", "description", "priority")
        widgets = {
            "subject": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
            "priority": forms.Select(attrs={"class": "form-select"}),
        }
