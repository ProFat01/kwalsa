"""
v1.2 Feature 1 & 2: the analytics member-management filter dashboard, and
its "Open Members" link into apps.members.staff_member_list_view.

These tests exist alongside test_views.py / test_services.py rather than
inside them, so the existing analytics test files stay untouched.
"""
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.core.models import Association
from apps.members.models import Member


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
class MemberManagementDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles", verbosity=0)
        cls.association = Association.objects.create(
            name="Malam Sidi Students Association", short_name="MSA", slug="msa"
        )

        cls.approved_science = _member(
            cls.association, full_name="Amina Yusuf", phone_number="0801111111", nin_number="11111111111",
            faculty="Science", department="Computer Science", level="400", gender=Member.Gender.FEMALE,
        )
        cls.approved_science.approval_status = Member.ApprovalStatus.APPROVED
        cls.approved_science.save()

        cls.pending_arts = _member(
            cls.association, full_name="Bello Musa", phone_number="0802222222", nin_number="22222222222",
            faculty="Arts", department="History", level="200", gender=Member.Gender.MALE,
        )
        # left at the model default (pending)

        cls.approved_arts = _member(
            cls.association, full_name="Chidi Okafor", phone_number="0803333333", nin_number="33333333333",
            faculty="Arts", department="History", level="200", gender=Member.Gender.MALE,
        )
        cls.approved_arts.approval_status = Member.ApprovalStatus.APPROVED
        cls.approved_arts.save()

        cls.analytics_admin = User.objects.create_user(username="ana", password="x", is_staff=True)
        cls.analytics_admin.groups.add(Group.objects.get(name="Analytics Admin"))

    def test_requires_login(self):
        response = self.client.get(reverse("analytics:member_management_dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_unfiltered_shows_every_member(self):
        self.client.login(username="ana", password="x")
        response = self.client.get(reverse("analytics:member_management_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["overview"]["total"], 3)

    def test_faculty_filter_narrows_total(self):
        self.client.login(username="ana", password="x")
        response = self.client.get(reverse("analytics:member_management_dashboard"), {"faculty": "Arts"})
        self.assertEqual(response.context["overview"]["total"], 2)

    def test_combined_filters_are_anded(self):
        self.client.login(username="ana", password="x")
        response = self.client.get(
            reverse("analytics:member_management_dashboard"),
            {"faculty": "Arts", "approval_status": Member.ApprovalStatus.APPROVED},
        )
        self.assertEqual(response.context["overview"]["total"], 1)

    def test_status_breakdown_matches_filtered_set(self):
        self.client.login(username="ana", password="x")
        response = self.client.get(reverse("analytics:member_management_dashboard"), {"faculty": "Arts"})
        breakdown = {row["value"]: row["count"] for row in response.context["overview"]["status_breakdown"]}
        self.assertEqual(breakdown["approved"], 1)
        self.assertEqual(breakdown["pending"], 1)
        self.assertEqual(breakdown["rejected"], 0)

    def test_open_members_link_carries_the_same_querystring(self):
        self.client.login(username="ana", password="x")
        response = self.client.get(reverse("analytics:member_management_dashboard"), {"faculty": "Arts"})
        self.assertContains(response, reverse("members:staff_list"))
        self.assertContains(response, "faculty=Arts")


@override_settings(DEFAULT_ASSOCIATION_SLUG="msa")
class OpenMembersRoundTripTests(TestCase):
    """
    Feature 2: what the dashboard counts for a given filter set must be
    exactly what the staff Members list shows for the same querystring —
    both go through apps.members.services.filter_members(), so this is
    really a test that they were wired to the *same* call, not two that
    happen to agree.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles", verbosity=0)
        cls.association = Association.objects.create(
            name="Malam Sidi Students Association", short_name="MSA", slug="msa"
        )
        _member(cls.association, full_name="In Filter", phone_number="0804444444", nin_number="44444444444", level="300")
        _member(cls.association, full_name="Out Of Filter", phone_number="0805555555", nin_number="55555555555", level="200")

        cls.super_admin = User.objects.create_user(username="root", password="x", is_staff=True)
        cls.super_admin.groups.add(Group.objects.get(name="Super Admin"))

    def test_member_list_matches_dashboard_count_for_same_filters(self):
        self.client.login(username="root", password="x")
        dashboard_response = self.client.get(reverse("analytics:member_management_dashboard"), {"level": "300"})
        total = dashboard_response.context["overview"]["total"]

        list_response = self.client.get(reverse("members:staff_list"), {"level": "300"})
        self.assertEqual(list_response.context["members"].paginator.count, total)
        self.assertContains(list_response, "In Filter")
        self.assertNotContains(list_response, "Out Of Filter")
