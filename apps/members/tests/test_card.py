from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse

from apps.core.models import Association
from apps.members.card_services import build_verification_url, generate_qr_png
from apps.members.models import Member, MembershipCard

from .helpers import MediaIsolatedTestCase, make_image

User = get_user_model()


def _make_approved_member(association, **overrides):
    defaults = dict(
        association=association,
        full_name="Aisha Bello",
        phone_number="08012345678",
        nin_number="12345678901",
        date_of_birth="2002-05-14",
        institution="Malam Sidi College",
        course="Computer Science",
        category=Member.Category.UNDERGRADUATE,
        passport_photo=make_image("photo.png"),
        approval_status=Member.ApprovalStatus.APPROVED,
        membership_id="MSA-0001",
        voting_status=True,
    )
    defaults.update(overrides)
    return Member.objects.create(**defaults)


@override_settings(DEFAULT_ASSOCIATION_SLUG="msa")
class MembershipCardModelTests(MediaIsolatedTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.association = Association.objects.create(
            name="Malam Sidi Students Association", short_name="MSA", slug="msa"
        )

    def test_get_or_create_for_is_idempotent(self):
        member = _make_approved_member(self.association)
        card_1 = MembershipCard.get_or_create_for(member)
        card_2 = MembershipCard.get_or_create_for(member)
        self.assertEqual(card_1.pk, card_2.pk)
        self.assertEqual(MembershipCard.objects.filter(member=member).count(), 1)

    def test_each_member_gets_a_distinct_card_uuid(self):
        member_1 = _make_approved_member(self.association, phone_number="08011111111", nin_number="11111111111")
        member_2 = _make_approved_member(
            self.association, phone_number="08022222222", nin_number="22222222222", membership_id="MSA-0002"
        )
        card_1 = MembershipCard.get_or_create_for(member_1)
        card_2 = MembershipCard.get_or_create_for(member_2)
        self.assertNotEqual(card_1.card_uuid, card_2.card_uuid)


class QrGenerationTests(MediaIsolatedTestCase):
    def test_generate_qr_png_returns_valid_png_bytes(self):
        png_bytes = generate_qr_png("https://example.com/members/verify/abc/")
        self.assertTrue(png_bytes.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(len(png_bytes), 100)


@override_settings(DEFAULT_ASSOCIATION_SLUG="msa")
class PortalCardViewTests(MediaIsolatedTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.association = Association.objects.create(
            name="Malam Sidi Students Association", short_name="MSA", slug="msa"
        )

    def _login_portal(self, member):
        session = self.client.session
        session["portal_member_id"] = member.pk
        session.save()

    def test_anonymous_redirected_to_portal_login(self):
        response = self.client.get(reverse("members:portal_card"))
        self.assertRedirects(response, reverse("members:portal_login"))

    def test_logged_in_member_can_view_own_card(self):
        member = _make_approved_member(self.association)
        self._login_portal(member)

        response = self.client.get(reverse("members:portal_card"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, member.full_name)
        self.assertContains(response, member.membership_id)
        # card row is created lazily on first view
        self.assertTrue(MembershipCard.objects.filter(member=member).exists())

    def test_card_qr_endpoint_returns_png(self):
        member = _make_approved_member(self.association)
        self._login_portal(member)

        response = self.client.get(reverse("members:portal_card_qr"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")

    def test_rejected_member_loses_card_access(self):
        member = _make_approved_member(self.association, approval_status=Member.ApprovalStatus.REJECTED)
        self._login_portal(member)

        response = self.client.get(reverse("members:portal_card"))
        self.assertRedirects(response, reverse("members:portal_login"))


@override_settings(DEFAULT_ASSOCIATION_SLUG="msa")
class StaffCardViewTests(MediaIsolatedTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.association = Association.objects.create(
            name="Malam Sidi Students Association", short_name="MSA", slug="msa"
        )

    def setUp(self):
        call_command("setup_roles", verbosity=0)

    def test_anonymous_redirected_to_admin_login(self):
        member = _make_approved_member(self.association)
        response = self.client.get(reverse("members:staff_card", args=[member.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_staff_without_member_permission_gets_403(self):
        member = _make_approved_member(self.association)
        User.objects.create_user(username="plainstaff", password="x", is_staff=True)
        self.client.login(username="plainstaff", password="x")

        response = self.client.get(reverse("members:staff_card", args=[member.pk]))
        self.assertEqual(response.status_code, 403)

    def test_registration_admin_can_view_member_card(self):
        member = _make_approved_member(self.association)
        admin_user = User.objects.create_user(username="reg_admin", password="x", is_staff=True)
        admin_user.groups.add(Group.objects.get(name="Registration Admin"))
        self.client.login(username="reg_admin", password="x")

        response = self.client.get(reverse("members:staff_card", args=[member.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, member.full_name)


@override_settings(DEFAULT_ASSOCIATION_SLUG="msa")
class VerifyMemberViewTests(MediaIsolatedTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.association = Association.objects.create(
            name="Malam Sidi Students Association", short_name="MSA", slug="msa"
        )

    def test_valid_card_shows_valid_member(self):
        member = _make_approved_member(self.association)
        card = MembershipCard.get_or_create_for(member)

        response = self.client.get(reverse("members:verify_member", args=[card.card_uuid]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Valid Member")
        self.assertContains(response, member.full_name)

    def test_unapproved_member_card_shows_invalid(self):
        member = _make_approved_member(self.association, approval_status=Member.ApprovalStatus.PENDING)
        card = MembershipCard.get_or_create_for(member)

        response = self.client.get(reverse("members:verify_member", args=[card.card_uuid]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid Membership")
        self.assertNotContains(response, member.full_name)

    def test_unknown_uuid_shows_invalid_not_404(self):
        import uuid

        response = self.client.get(reverse("members:verify_member", args=[uuid.uuid4()]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid Membership")

    def test_verification_page_does_not_expose_sensitive_fields(self):
        member = _make_approved_member(self.association)
        card = MembershipCard.get_or_create_for(member)

        response = self.client.get(reverse("members:verify_member", args=[card.card_uuid]))
        self.assertNotContains(response, member.nin_number)
        self.assertNotContains(response, member.phone_number)
        self.assertNotContains(response, str(member.date_of_birth))

    def test_verification_url_is_absolute_and_uses_card_uuid(self):
        from django.test import RequestFactory

        member = _make_approved_member(self.association)
        card = MembershipCard.get_or_create_for(member)

        request = RequestFactory().get("/")
        url = build_verification_url(request, card)
        self.assertTrue(url.startswith("http"))
        self.assertIn(str(card.card_uuid), url)
