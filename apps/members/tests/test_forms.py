from apps.core.models import Association
from apps.members.forms import MemberRegistrationForm
from apps.members.models import Member, RegistrationApplication

from .helpers import MediaIsolatedTestCase, make_image


def _valid_form_data(**overrides):
    data = {
        "full_name": "Aisha Bello",
        "phone_number": "08012345678",
        "nin_number": "12345678901",
        "date_of_birth": "2002-05-14",
        "institution": "Malam Sidi College",
        "course": "Computer Science",
        "category": Member.Category.UNDERGRADUATE,
    }
    data.update(overrides)
    return data


class MemberRegistrationFormTests(MediaIsolatedTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.association = Association.objects.create(name="Malam Sidi Students Association", short_name="MSA")

    def _files(self):
        return {"passport_photo": make_image("photo.png"), "receipt_image": make_image("receipt.png")}

    def test_successful_registration_creates_member_and_pending_application(self):
        form = MemberRegistrationForm(data=_valid_form_data(), files=self._files())
        self.assertTrue(form.is_valid(), form.errors)

        application = form.save(association=self.association)

        self.assertEqual(Member.objects.count(), 1)
        member = Member.objects.first()
        self.assertEqual(member.association, self.association)
        self.assertIsNone(member.membership_id)
        self.assertEqual(member.approval_status, Member.ApprovalStatus.PENDING)

        self.assertEqual(application.member, member)
        self.assertEqual(application.status, RegistrationApplication.Status.PENDING)
        self.assertTrue(application.application_number.startswith("APP-"))

    def test_invalid_phone_prefix_rejected_with_clear_message(self):
        form = MemberRegistrationForm(data=_valid_form_data(phone_number="06012345678"), files=self._files())
        self.assertFalse(form.is_valid())
        self.assertIn("phone_number", form.errors)
        self.assertIn("must start with one of", form.errors["phone_number"][0])

    def test_invalid_nin_length_rejected_with_clear_message(self):
        form = MemberRegistrationForm(data=_valid_form_data(nin_number="123"), files=self._files())
        self.assertFalse(form.is_valid())
        self.assertIn("nin_number", form.errors)
        self.assertIn("exactly 11 digits", form.errors["nin_number"][0])

    def test_duplicate_phone_only(self):
        Member.objects.create(
            association=self.association, full_name="Existing", phone_number="08012345678",
            nin_number="11111111111", date_of_birth="2000-01-01", institution="X", course="Y",
            category=Member.Category.UNDERGRADUATE, passport_photo="members/passports/x.jpg",
        )
        form = MemberRegistrationForm(
            data=_valid_form_data(phone_number="08012345678", nin_number="22222222222"),
            files=self._files(),
        )
        self.assertFalse(form.is_valid())
        self.assertIn("Phone Number Already Registered.", form.errors["__all__"])
        self.assertTrue(form.duplicate_detected)

    def test_duplicate_nin_only(self):
        Member.objects.create(
            association=self.association, full_name="Existing", phone_number="08099999999",
            nin_number="12345678901", date_of_birth="2000-01-01", institution="X", course="Y",
            category=Member.Category.UNDERGRADUATE, passport_photo="members/passports/x.jpg",
        )
        form = MemberRegistrationForm(
            data=_valid_form_data(phone_number="08012345678", nin_number="12345678901"),
            files=self._files(),
        )
        self.assertFalse(form.is_valid())
        self.assertIn("NIN Number Already Registered.", form.errors["__all__"])
        self.assertTrue(form.duplicate_detected)

    def test_duplicate_both_phone_and_nin(self):
        Member.objects.create(
            association=self.association, full_name="Existing", phone_number="08012345678",
            nin_number="12345678901", date_of_birth="2000-01-01", institution="X", course="Y",
            category=Member.Category.UNDERGRADUATE, passport_photo="members/passports/x.jpg",
        )
        form = MemberRegistrationForm(data=_valid_form_data(), files=self._files())
        self.assertFalse(form.is_valid())
        self.assertIn("Membership Record Already Exists.", form.errors["__all__"])
        self.assertTrue(form.duplicate_detected)

    def test_no_duplicate_detected_flag_on_clean_submission(self):
        form = MemberRegistrationForm(data=_valid_form_data(), files=self._files())
        self.assertTrue(form.is_valid())
        self.assertFalse(getattr(form, "duplicate_detected", False))
