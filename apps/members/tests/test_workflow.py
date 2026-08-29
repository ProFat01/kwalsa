import os

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.core.models import Association
from apps.members.models import Member, MembershipCard, RegistrationApplication

from .helpers import MediaIsolatedTestCase, make_image


class ApprovalWorkflowTests(MediaIsolatedTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.association = Association.objects.create(name="Malam Sidi Students Association", short_name="MSA")

    def _make_application(self, **member_overrides):
        defaults = dict(
            association=self.association, full_name="Test Member", phone_number="08012345678",
            nin_number="12345678901", date_of_birth="2001-01-01", institution="X", course="Y",
            category=Member.Category.UNDERGRADUATE,
        )
        defaults.update(member_overrides)
        member = Member.objects.create(passport_photo=make_image("p.png"), **defaults)
        application = RegistrationApplication.objects.create(member=member, receipt_image=make_image("r.png"))
        return member, application

    def test_approval_generates_membership_id_and_sets_eligibility(self):
        member, application = self._make_application()
        self.assertIsNone(member.membership_id)

        application.status = RegistrationApplication.Status.APPROVED
        application.save()
        member.refresh_from_db()

        self.assertEqual(member.approval_status, Member.ApprovalStatus.APPROVED)
        self.assertTrue(member.voting_status)
        self.assertIsNotNone(member.membership_id)
        self.assertTrue(member.membership_id.startswith("MSA-"))

    def test_membership_id_increments_across_members(self):
        member1, app1 = self._make_application(phone_number="08011111111", nin_number="11111111111")
        member2, app2 = self._make_application(phone_number="08022222222", nin_number="22222222222")

        app1.status = RegistrationApplication.Status.APPROVED
        app1.save()
        app2.status = RegistrationApplication.Status.APPROVED
        app2.save()

        member1.refresh_from_db()
        member2.refresh_from_db()
        self.assertNotEqual(member1.membership_id, member2.membership_id)

    def test_rejection_requires_a_reason(self):
        member, application = self._make_application()
        application.status = RegistrationApplication.Status.REJECTED
        with self.assertRaises(ValidationError) as ctx:
            application.full_clean(exclude=["application_number"])
        self.assertIn("rejection_reason", ctx.exception.message_dict)

    def test_rejection_with_reason_updates_member_and_blocks_voting(self):
        member, application = self._make_application()
        application.status = RegistrationApplication.Status.REJECTED
        application.rejection_reason = "Receipt unreadable."
        application.save()
        member.refresh_from_db()

        self.assertEqual(member.approval_status, Member.ApprovalStatus.REJECTED)
        self.assertFalse(member.voting_status)
        self.assertIsNone(member.membership_id)

    def test_receipt_deleted_from_disk_after_approval(self):
        member, application = self._make_application()
        receipt_path = application.receipt_image.path
        self.assertTrue(os.path.exists(receipt_path))

        application.status = RegistrationApplication.Status.APPROVED
        application.save()
        application.refresh_from_db()

        self.assertFalse(application.receipt_image)
        self.assertFalse(os.path.exists(receipt_path))

    def test_receipt_deleted_from_disk_after_rejection(self):
        member, application = self._make_application()
        receipt_path = application.receipt_image.path
        self.assertTrue(os.path.exists(receipt_path))

        application.status = RegistrationApplication.Status.REJECTED
        application.rejection_reason = "Duplicate payment receipt."
        application.save()
        application.refresh_from_db()

        self.assertFalse(application.receipt_image)
        self.assertFalse(os.path.exists(receipt_path))

    def test_editing_a_reviewed_application_again_does_not_re_trigger_member_sync(self):
        """
        Saving an already-approved application again (e.g. fixing a typo
        in an unrelated field) must not regenerate a second membership_id
        or re-run the receipt cleanup logic — the signal only acts on a
        genuine status *transition*, not every save.
        """
        member, application = self._make_application()
        application.status = RegistrationApplication.Status.APPROVED
        application.save()
        member.refresh_from_db()
        first_membership_id = member.membership_id

        application.save()  # status unchanged this time
        member.refresh_from_db()
        self.assertEqual(member.membership_id, first_membership_id)


class UniquenessConstraintTests(MediaIsolatedTestCase):
    """PART 8: no duplicate NIN/phone/membership_id/application_number — enforced at the DB level."""

    @classmethod
    def setUpTestData(cls):
        cls.association = Association.objects.create(name="Malam Sidi Students Association", short_name="MSA")

    def test_duplicate_phone_number_rejected_at_db_level(self):
        Member.objects.create(
            association=self.association, full_name="A", phone_number="08012345678",
            nin_number="11111111111", date_of_birth="2001-01-01", institution="X", course="Y",
            category=Member.Category.UNDERGRADUATE, passport_photo=make_image("a.png"),
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Member.objects.create(
                    association=self.association, full_name="B", phone_number="08012345678",
                    nin_number="22222222222", date_of_birth="2001-01-01", institution="X", course="Y",
                    category=Member.Category.UNDERGRADUATE, passport_photo=make_image("b.png"),
                )

    def test_duplicate_nin_rejected_at_db_level(self):
        Member.objects.create(
            association=self.association, full_name="A", phone_number="08011111111",
            nin_number="12345678901", date_of_birth="2001-01-01", institution="X", course="Y",
            category=Member.Category.UNDERGRADUATE, passport_photo=make_image("a.png"),
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Member.objects.create(
                    association=self.association, full_name="B", phone_number="08022222222",
                    nin_number="12345678901", date_of_birth="2001-01-01", institution="X", course="Y",
                    category=Member.Category.UNDERGRADUATE, passport_photo=make_image("b.png"),
                )

    def test_application_numbers_are_unique_and_sequential(self):
        member = Member.objects.create(
            association=self.association, full_name="A", phone_number="08011111111",
            nin_number="11111111111", date_of_birth="2001-01-01", institution="X", course="Y",
            category=Member.Category.UNDERGRADUATE, passport_photo=make_image("a.png"),
        )
        app1 = RegistrationApplication.objects.create(member=member, receipt_image=make_image("r1.png"))
        # simulate reapplication after a hypothetical rejection
        app2 = RegistrationApplication.objects.create(member=member, receipt_image=make_image("r2.png"))
        self.assertNotEqual(app1.application_number, app2.application_number)
        self.assertTrue(app1.application_number.startswith("APP-"))
        self.assertTrue(app2.application_number.startswith("APP-"))


class ApprovalInvariantSelfHealingTests(MediaIsolatedTestCase):
    """
    v1.2.1 regression tests. Root cause: the "Approved ⇒ has a
    membership_id AND is voting-eligible" invariant used to live only in
    members/signals.py, as a side effect of a RegistrationApplication
    transitioning to Approved. Any other way a Member ended up with
    approval_status == Approved (a direct edit in the Member admin —
    approval_status was never read-only there — a script, stale
    production data from before this fix) silently kept an empty
    membership_id and voting_status False. The fix moved the invariant
    into Member.save() itself, so it holds regardless of path and heals
    itself the next time an inconsistent record is saved.
    """

    @classmethod
    def setUpTestData(cls):
        cls.association = Association.objects.create(name="Malam Sidi Students Association", short_name="MSA")

    def _make_member(self, **overrides):
        defaults = dict(
            association=self.association, full_name="Test Member", phone_number="08012345678",
            nin_number="12345678901", date_of_birth="2001-01-01", institution="X", course="Y",
            category=Member.Category.UNDERGRADUATE,
        )
        defaults.update(overrides)
        return Member.objects.create(passport_photo=make_image("p.png"), **defaults)

    def _make_application(self, **member_overrides):
        member = self._make_member(**member_overrides)
        application = RegistrationApplication.objects.create(member=member, receipt_image=make_image("r.png"))
        return member, application

    def test_delayed_approval_after_newer_applicants_gets_next_available_id_not_a_historical_slot(self):
        """An applicant who sat Pending while later applicants were approved must not collide with,
        or try to insert itself into, IDs already handed out while it waited."""
        old_member, old_application = self._make_application(phone_number="08010000001", nin_number="10000000001")

        newer_ids = []
        for i in range(3):
            member, application = self._make_application(
                phone_number=f"0801100000{i}", nin_number=f"1000000010{i}"
            )
            application.status = RegistrationApplication.Status.APPROVED
            application.save()
            member.refresh_from_db()
            newer_ids.append(member.membership_id)

        old_application.status = RegistrationApplication.Status.APPROVED
        old_application.save()
        old_member.refresh_from_db()

        self.assertIsNotNone(old_member.membership_id)
        self.assertTrue(old_member.voting_status)
        self.assertNotIn(old_member.membership_id, newer_ids)
        self.assertEqual(len({old_member.membership_id, *newer_ids}), 4)  # all four distinct

    def test_previously_rejected_then_reapproved_gets_a_valid_membership_id(self):
        member, application = self._make_application()
        application.status = RegistrationApplication.Status.REJECTED
        application.rejection_reason = "Receipt unreadable."
        application.save()
        member.refresh_from_db()
        self.assertIsNone(member.membership_id)
        self.assertFalse(member.voting_status)

        reapplication = RegistrationApplication.objects.create(member=member, receipt_image=make_image("r2.png"))
        reapplication.status = RegistrationApplication.Status.APPROVED
        reapplication.save()
        member.refresh_from_db()

        self.assertEqual(member.approval_status, Member.ApprovalStatus.APPROVED)
        self.assertTrue(member.voting_status)
        self.assertIsNotNone(member.membership_id)

    def test_approved_member_missing_membership_id_is_healed_on_save(self):
        """Simulates pre-existing bad production data: Approved, but membership_id never got set
        (e.g. it was cleared, or the record predates this fix). Saving it again must repair it,
        with no manual SQL and no special call — just .save(). QuerySet.update() bypasses
        Member.save() entirely, which is exactly how such a record could have gotten into this
        state in the first place (and is the cleanest way to simulate it here)."""
        member = self._make_member()
        Member.objects.filter(pk=member.pk).update(
            approval_status=Member.ApprovalStatus.APPROVED, voting_status=True
        )
        member.refresh_from_db()
        self.assertIsNone(member.membership_id)

        member.save()
        member.refresh_from_db()

        self.assertIsNotNone(member.membership_id)
        self.assertTrue(member.membership_id.startswith("MSA-"))

    def test_approved_member_with_voting_status_false_is_healed_on_save(self):
        member = self._make_member()
        Member.objects.filter(pk=member.pk).update(approval_status=Member.ApprovalStatus.APPROVED)
        member.refresh_from_db()
        self.assertFalse(member.voting_status)

        member.save()
        member.refresh_from_db()

        self.assertTrue(member.voting_status)
        self.assertIsNotNone(member.membership_id)

    def test_directly_approving_a_member_outside_the_application_workflow_still_heals(self):
        """Covers the actual root cause: approval_status changed on Member directly
        (e.g. via the Member admin form, or any future code path), never through
        RegistrationApplication at all."""
        member = self._make_member()
        self.assertEqual(member.approval_status, Member.ApprovalStatus.PENDING)

        member.approval_status = Member.ApprovalStatus.APPROVED
        member.save()
        member.refresh_from_db()

        self.assertTrue(member.voting_status)
        self.assertIsNotNone(member.membership_id)

    def test_saving_an_already_approved_member_twice_does_not_change_or_duplicate_the_id(self):
        member = self._make_member(approval_status=Member.ApprovalStatus.APPROVED)
        member.save()
        member.refresh_from_db()
        first_id = member.membership_id
        self.assertIsNotNone(first_id)

        member.save()
        member.refresh_from_db()
        self.assertEqual(member.membership_id, first_id)

    def test_healing_many_stale_approved_members_produces_no_duplicate_ids(self):
        """Backward compatibility: several pre-existing Approved-but-broken records,
        healed independently, must still each get a unique membership_id."""
        members = [
            self._make_member(phone_number=f"0803000000{i}", nin_number=f"1300000030{i}")
            for i in range(4)
        ]
        Member.objects.filter(pk__in=[m.pk for m in members]).update(
            approval_status=Member.ApprovalStatus.APPROVED
        )
        for member in members:
            member.refresh_from_db()
            self.assertIsNone(member.membership_id)
            member.save()

        healed_ids = [Member.objects.get(pk=m.pk).membership_id for m in members]
        self.assertTrue(all(healed_ids))
        self.assertEqual(len(set(healed_ids)), len(healed_ids))

    def test_membership_card_and_qr_verification_work_after_healing(self):
        member = self._make_member(approval_status=Member.ApprovalStatus.APPROVED, voting_status=False)
        member.save()  # heals membership_id + voting_status
        member.refresh_from_db()

        card = MembershipCard.get_or_create_for(member)
        self.assertIsNotNone(card.card_uuid)

        response = self.client.get(reverse("members:verify_member", args=[card.card_uuid]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, member.membership_id)
        self.assertContains(response, "Valid Member")  # verify.html's valid-card badge
