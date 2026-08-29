from django.test import override_settings
from django.urls import reverse

from apps.core.models import Association
from apps.members.models import Member, RegistrationApplication

from .helpers import MediaIsolatedTestCase, make_image


def _registration_post_data(**overrides):
    data = {
        "full_name": "Aisha Bello",
        "phone_number": "08012345678",
        "nin_number": "12345678901",
        "date_of_birth": "2002-05-14",
        "institution": "Malam Sidi College",
        "course": "Computer Science",
        "category": Member.Category.UNDERGRADUATE,
        "passport_photo": make_image("photo.png"),
        "receipt_image": make_image("receipt.png"),
    }
    data.update(overrides)
    return data


@override_settings(DEFAULT_ASSOCIATION_SLUG="msa")
class RegisterViewTests(MediaIsolatedTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.association = Association.objects.create(
            name="Malam Sidi Students Association", short_name="MSA", slug="msa"
        )

    def test_get_register_page(self):
        response = self.client.get(reverse("members:register"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Membership Registration")

    def test_successful_registration_redirects_to_success_page_with_application_number(self):
        response = self.client.post(reverse("members:register"), _registration_post_data())
        self.assertEqual(response.status_code, 302)

        application = RegistrationApplication.objects.get()
        self.assertIn(application.application_number, response["Location"])

        success_response = self.client.get(response["Location"])
        self.assertContains(success_response, "Registration Submitted Successfully.")
        self.assertContains(success_response, application.application_number)

    def test_duplicate_registration_shows_recovery_message_and_cta(self):
        self.client.post(reverse("members:register"), _registration_post_data())
        response = self.client.post(
            reverse("members:register"),
            _registration_post_data(nin_number="99999999999"),  # same phone, different NIN
        )
        self.assertContains(response, "Phone Number Already Registered.")
        self.assertContains(response, "You already have a registration record.")
        self.assertContains(response, reverse("members:status_check"))

    def test_registration_unavailable_when_no_association_configured(self):
        Association.objects.all().delete()
        response = self.client.get(reverse("members:register"))
        self.assertContains(response, "Registration is not currently available")


class StatusCheckViewTests(MediaIsolatedTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.association = Association.objects.create(name="Malam Sidi Students Association", short_name="MSA")

        cls.pending_member = Member.objects.create(
            association=cls.association, full_name="Pending Person", phone_number="08011111111",
            nin_number="11111111111", date_of_birth="2001-01-01", institution="X", course="Y",
            category=Member.Category.UNDERGRADUATE, passport_photo="members/passports/x.jpg",
        )
        cls.pending_app = RegistrationApplication.objects.create(member=cls.pending_member)

        cls.approved_member = Member.objects.create(
            association=cls.association, full_name="Approved Person", phone_number="08022222222",
            nin_number="22222222222", date_of_birth="2001-01-01", institution="X", course="Y",
            category=Member.Category.UNDERGRADUATE, passport_photo="members/passports/x.jpg",
        )
        cls.approved_app = RegistrationApplication.objects.create(member=cls.approved_member)
        cls.approved_app.status = RegistrationApplication.Status.APPROVED
        cls.approved_app.save()
        cls.approved_member.refresh_from_db()

        cls.rejected_member = Member.objects.create(
            association=cls.association, full_name="Rejected Person", phone_number="08033333333",
            nin_number="33333333333", date_of_birth="2001-01-01", institution="X", course="Y",
            category=Member.Category.UNDERGRADUATE, passport_photo="members/passports/x.jpg",
        )
        cls.rejected_app = RegistrationApplication.objects.create(member=cls.rejected_member)
        cls.rejected_app.status = RegistrationApplication.Status.REJECTED
        cls.rejected_app.rejection_reason = "Receipt did not match registration fee."
        cls.rejected_app.save()

    def test_get_status_check_page(self):
        response = self.client.get(reverse("members:status_check"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Check Registration Status")

    def test_lookup_by_application_number_pending(self):
        response = self.client.post(reverse("members:status_check"), {
            "search_by": "application_number", "application_number": self.pending_app.application_number,
        })
        self.assertContains(response, "Status: Pending Review")

    def test_lookup_by_application_number_approved_shows_membership_id(self):
        response = self.client.post(reverse("members:status_check"), {
            "search_by": "application_number", "application_number": self.approved_app.application_number,
        })
        self.assertContains(response, "Status: Approved")
        self.assertContains(response, self.approved_member.membership_id)

    def test_lookup_by_application_number_rejected_shows_reason(self):
        response = self.client.post(reverse("members:status_check"), {
            "search_by": "application_number", "application_number": self.rejected_app.application_number,
        })
        self.assertContains(response, "Status: Rejected")
        self.assertContains(response, "Receipt did not match registration fee.")

    def test_lookup_by_nin_and_phone(self):
        response = self.client.post(reverse("members:status_check"), {
            "search_by": "nin_phone",
            "nin_number": self.approved_member.nin_number,
            "phone_number": self.approved_member.phone_number,
        })
        self.assertContains(response, "Status: Approved")
        self.assertContains(response, self.approved_member.membership_id)

    def test_lookup_not_found(self):
        response = self.client.post(reverse("members:status_check"), {
            "search_by": "application_number", "application_number": "APP-2026-99999",
        })
        self.assertContains(response, "No registration record found.")

    def test_nin_phone_mode_requires_both_fields(self):
        response = self.client.post(reverse("members:status_check"), {
            "search_by": "nin_phone", "nin_number": "11111111111", "phone_number": "",
        })
        self.assertContains(response, "Please enter both your NIN and phone number.")
