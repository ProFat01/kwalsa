"""
apps.accounts.forms — v1.2 Communication Center (Features 5, 6, 10).
"""
from django import forms

from apps.members.models import Member
from apps.members.services import FILTERABLE_MEMBER_FIELDS

from .models import Announcement


class AnnouncementComposeForm(forms.Form):
    """
    One form covers compose (subject/message), targeting (recipient_type +
    the filter that type needs), and delivery method — Feature 6's "any
    combination of filters" is satisfied by recipient_type=custom, which
    lets faculty/department/level/gender/approval_status all be set at
    once (AND-combined, same as the analytics filter dashboard).

    Validation (Feature 10): every field is validated server-side
    regardless of what the client sent — subject/message are required, a
    recipient type must resolve to at least the *possibility* of
    recipients, and delivery_method is hard-locked to "email" here so a
    tampered form value can't queue an SMS/Push send that would silently
    no-op or error deep inside notifications.py.
    """

    subject = forms.CharField(max_length=255)
    message = forms.CharField(widget=forms.Textarea(attrs={"rows": 8}))

    recipient_type = forms.ChoiceField(choices=Announcement.RecipientType.choices)
    faculty = forms.CharField(required=False, max_length=255)
    department = forms.CharField(required=False, max_length=255)
    level = forms.CharField(required=False, max_length=20)
    gender = forms.ChoiceField(choices=[("", "---")] + list(Member.Gender.choices), required=False)
    approval_status = forms.ChoiceField(
        choices=[("", "---")] + list(Member.ApprovalStatus.choices), required=False
    )
    selected_member_ids = forms.CharField(required=False, widget=forms.HiddenInput)

    delivery_method = forms.ChoiceField(
        choices=Announcement.DeliveryMethod.choices, initial=Announcement.DeliveryMethod.EMAIL
    )

    def clean_delivery_method(self):
        value = self.cleaned_data["delivery_method"]
        if value != Announcement.DeliveryMethod.EMAIL:
            raise forms.ValidationError(
                "Only Email delivery is available right now. SMS and Push Notification are coming soon."
            )
        return value

    def clean(self):
        cleaned = super().clean()
        recipient_type = cleaned.get("recipient_type")

        if recipient_type == Announcement.RecipientType.SELECTED and not cleaned.get("selected_member_ids"):
            raise forms.ValidationError("Select at least one member to send to.")

        if recipient_type == Announcement.RecipientType.FACULTY and not cleaned.get("faculty"):
            raise forms.ValidationError("Choose a faculty to target.")
        if recipient_type == Announcement.RecipientType.DEPARTMENT and not cleaned.get("department"):
            raise forms.ValidationError("Choose a department to target.")
        if recipient_type == Announcement.RecipientType.LEVEL and not cleaned.get("level"):
            raise forms.ValidationError("Choose a level to target.")
        if recipient_type == Announcement.RecipientType.GENDER and not cleaned.get("gender"):
            raise forms.ValidationError("Choose a gender to target.")

        return cleaned

    def selected_ids(self):
        raw = self.cleaned_data.get("selected_member_ids") or ""
        ids = []
        for chunk in raw.split(","):
            chunk = chunk.strip()
            if chunk.isdigit():
                ids.append(int(chunk))
        return ids

    def filters(self):
        return {field: self.cleaned_data.get(field) or "" for field in FILTERABLE_MEMBER_FIELDS}
