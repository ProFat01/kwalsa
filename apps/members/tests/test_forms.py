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
        "institution": "Gombe State University (GSU), Tudun Wada",
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

    def test_gender_is_optional(self):
        # Matches Member.gender's own blank=True (see models.py) — a
        # registrant who declines to answer must not be blocked.
        form = MemberRegistrationForm(data=_valid_form_data(), files=self._files())
        self.assertTrue(form.is_valid(), form.errors)
        application = form.save(association=self.association)
        self.assertEqual(application.member.gender, "")

    def test_valid_gender_choice_is_saved_on_the_member(self):
        form = MemberRegistrationForm(
            data=_valid_form_data(gender=Member.Gender.FEMALE), files=self._files()
        )
        self.assertTrue(form.is_valid(), form.errors)
        application = form.save(association=self.association)
        self.assertEqual(application.member.gender, Member.Gender.FEMALE)

    def test_invalid_gender_value_rejected(self):
        form = MemberRegistrationForm(
            data=_valid_form_data(gender="nonbinary-not-a-real-choice"), files=self._files()
        )
        self.assertFalse(form.is_valid())
        self.assertIn("gender", form.errors)

    def test_selecting_a_listed_institution_saves_it_verbatim(self):
        form = MemberRegistrationForm(
            data=_valid_form_data(institution="Federal University Kashere (FUK)"), files=self._files()
        )
        self.assertTrue(form.is_valid(), form.errors)
        application = form.save(association=self.association)
        self.assertEqual(application.member.institution, "Federal University Kashere (FUK)")

    def test_selecting_other_and_typing_a_custom_institution_saves_the_typed_value(self):
        form = MemberRegistrationForm(
            data=_valid_form_data(institution="other", institution_other="Kwalsa Community College"),
            files=self._files(),
        )
        self.assertTrue(form.is_valid(), form.errors)
        application = form.save(association=self.association)
        self.assertEqual(application.member.institution, "Kwalsa Community College")

    def test_selecting_other_without_typing_anything_is_rejected(self):
        form = MemberRegistrationForm(
            data=_valid_form_data(institution="other", institution_other=""), files=self._files()
        )
        self.assertFalse(form.is_valid())
        self.assertIn("institution_other", form.errors)

    def test_arbitrary_institution_text_not_in_the_seed_list_is_rejected(self):
        # Anything not in institutions.INSTITUTION_CHOICES and not routed
        # through the "other" + institution_other pair must fail --
        # otherwise the seeded dropdown would be trivially bypassable.
        form = MemberRegistrationForm(
            data=_valid_form_data(institution="Some Made Up University"), files=self._files()
        )
        self.assertFalse(form.is_valid())
        self.assertIn("institution", form.errors)
