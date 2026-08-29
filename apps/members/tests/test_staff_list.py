"""
v1.2 Feature 2 & 3: the staff Members list (reached via "Open Members")
and its per-row quick actions.
"""
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.core.models import Association
from apps.members.models import Member
from apps.members.services import member_filter_choices


def _member(association, **overrides):
    defaults = dict(
        full_name="Test Member",
        phone_number="0800000000",
        nin_number="00000000000",
        date_of_birth="2001-01-01",
        institution="Malam Sidi College",
        course="Computer Science",
        category=Member.Category.UNDERGRADUATE,
        passport_photo="members/passports/x.jpg",
        faculty="Science",
        department="Computer Science",
        level="400",
        gender=Member.Gender.FEMALE,
        email="member@example.com",
    )
    defaults.update(overrides)
    return Member.objects.create(association=association, **defaults)


@override_settings(DEFAULT_ASSOCIATION_SLUG="msa")
class StaffMemberListTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles", verbosity=0)
        cls.association = Association.objects.create(
            name="Malam Sidi Students Association", short_name="MSA", slug="msa"
        )
        cls.member_with_id = _member(
            cls.association, full_name="Has Membership ID", phone_number="0801111111",
            nin_number="11111111111", membership_id="MSA-2026-0001",
        )
        cls.member_no_email = _member(
            cls.association, full_name="No Email On File", phone_number="0802222222",
            nin_number="22222222222", email="",
        )

        cls.registration_admin = User.objects.create_user(username="reg", password="x", is_staff=True)
        cls.registration_admin.groups.add(Group.objects.get(name="Registration Admin"))

        cls.plain_staff = User.objects.create_user(username="plain", password="x", is_staff=True)

    def setUp(self):
        # member_filter_choices() is cached per-association (see
        # apps.members.services) — clear it so one test's cached choices
        # can never leak into another via a reused association pk.
        cache.clear()

    def test_requires_login(self):
        response = self.client.get(reverse("members:staff_list"))
        self.assertEqual(response.status_code, 302)

    def test_staff_without_view_member_permission_gets_403(self):
        self.client.login(username="plain", password="x")
        response = self.client.get(reverse("members:staff_list"))
        self.assertEqual(response.status_code, 403)

    def test_role_with_view_member_permission_can_view(self):
        # Registration Admin already holds members.view_member for the
        # existing admin changelist — reused here, no new permission.
        self.client.login(username="reg", password="x")
        response = self.client.get(reverse("members:staff_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Has Membership ID")
        self.assertContains(response, "No Email On File")

    def test_quick_actions_present_for_member_with_email(self):
        self.client.login(username="reg", password="x")
        response = self.client.get(reverse("members:staff_list"))
        self.assertContains(response, reverse("admin:members_member_change", args=[self.member_with_id.pk]))
        self.assertContains(response, reverse("members:staff_card", args=[self.member_with_id.pk]))
        self.assertContains(response, "Copy ID")

    def test_send_sms_is_a_reserved_placeholder_not_a_link(self):
        self.client.login(username="reg", password="x")
        response = self.client.get(reverse("members:staff_list"))
        self.assertContains(response, "Send SMS")
        self.assertContains(response, "row-action-reserved")

    def test_member_without_email_shows_reserved_send_email(self):
        self.client.login(username="reg", password="x")
        response = self.client.get(reverse("members:staff_list"))
        compose_url = reverse("accounts:communication_compose")
        # The member with an email gets a working Send Email link...
        self.assertContains(
            response,
            f"{compose_url}?recipient_type=selected&amp;selected_member_ids={self.member_with_id.pk}",
        )
        # ...the member without one does not get that link at all.
        self.assertNotContains(
            response,
            f"{compose_url}?recipient_type=selected&amp;selected_member_ids={self.member_no_email.pk}",
        )


class MemberFilterChoicesCachingTests(TestCase):
    """
    member_filter_choices() (used to populate the staff list's
    faculty/department/level filter dropdowns) is cached for a few
    minutes per association — added during the v2.0 load-testing pass,
    where it was the actual bottleneck on the staff member list page at
    scale (~37ms of the page's ~130ms at 10,000 members, versus ~4ms for
    the paginated member query itself). These tests exist so a future
    change to the caching can't silently return stale or cross-association
    data without a test failing.
    """

    @classmethod
    def setUpTestData(cls):
        cls.association = Association.objects.create(
            name="Malam Sidi Students Association", short_name="MSA", slug="msa-cache-test"
        )
        cls.other_association = Association.objects.create(
            name="Other Association", short_name="OTHER", slug="other-cache-test"
        )

    def setUp(self):
        cache.clear()

    def test_returns_distinct_sorted_non_blank_values(self):
        _member(self.association, faculty="Science", department="Physics", level="200",
                phone_number="0803000001", nin_number="30000000001")
        _member(self.association, faculty="Science", department="Chemistry", level="100",
                phone_number="0803000002", nin_number="30000000002")
        _member(self.association, faculty="", department="Physics", level="200",
                phone_number="0803000003", nin_number="30000000003")  # blank faculty excluded

        choices = member_filter_choices(self.association)
        self.assertEqual(choices["faculty"], ["Science"])
        self.assertEqual(choices["department"], ["Chemistry", "Physics"])
        self.assertEqual(choices["level"], ["100", "200"])

    def test_second_call_is_served_from_cache_not_the_database(self):
        _member(self.association, faculty="Science", phone_number="0803000004", nin_number="30000000004")
        member_filter_choices(self.association)  # primes the cache

        with self.assertNumQueries(0):
            member_filter_choices(self.association)

    def test_cache_is_isolated_per_association(self):
        _member(self.association, faculty="Science", phone_number="0803000005", nin_number="30000000005")
        _member(self.other_association, faculty="Arts", phone_number="0803000006", nin_number="30000000006")

        self.assertEqual(member_filter_choices(self.association)["faculty"], ["Science"])
        self.assertEqual(member_filter_choices(self.other_association)["faculty"], ["Arts"])
