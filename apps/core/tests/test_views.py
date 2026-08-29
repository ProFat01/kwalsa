import datetime

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Association, ContactMessage, SiteSettings
from apps.elections.models import Election
from apps.members.models import Member, RegistrationApplication
from apps.members.tests.helpers import MediaIsolatedTestCase, make_image


@override_settings(DEFAULT_ASSOCIATION_SLUG="msa")
class CoreViewsTestCase(MediaIsolatedTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.association = Association.objects.create(
            name="Malam Sidi Students Association", short_name="MSA", slug="msa"
        )
        cls.site_settings = SiteSettings.objects.create(
            association=cls.association,
            motto="Unity in Service",
            welcome_message="Welcome to MSA — register, vote, and stay informed.",
            about_text="Founded in 2015.",
            mission="To serve students.",
            vision="A thriving student body.",
            contact_email="msa@example.com",
            contact_phone="08000000000",
            address="Malam Sidi Campus",
        )


class LandingPageTests(CoreViewsTestCase):
    """PART 2: hero, about, statistics, election status, CTA."""

    def test_renders_for_anonymous_visitor(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)

    def test_hero_shows_name_motto_and_welcome_message(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "Malam Sidi Students Association")
        self.assertContains(response, "Unity in Service")
        self.assertContains(response, "Welcome to MSA")

    def test_hero_buttons_present(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "Register Now")
        self.assertContains(response, "Check Status")

    def test_hero_vote_now_hidden_when_no_active_election(self):
        """
        Module 2 explicitly requires the hero's third CTA to be
        conditional: "If an election is currently active, automatically
        display a third button: Vote Now. Otherwise hide it." This
        fixture has no Election at all, so it must not appear.
        """
        response = self.client.get(reverse("core:home"))
        self.assertNotContains(response, "Vote Now")

    def test_hero_vote_now_shown_when_election_is_active(self):
        now = timezone.now()
        election = Election.objects.create(
            association=self.association, name="Active Poll",
            start_datetime=now - datetime.timedelta(hours=1), end_datetime=now + datetime.timedelta(hours=1),
        )
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "Vote Now")
        self.assertContains(response, reverse("elections:voting_login", args=[election.pk]))

    def test_statistics_section_shows_live_membership_counts(self):
        member = Member.objects.create(
            association=self.association, full_name="A", phone_number="08010000001", nin_number="10000000001",
            date_of_birth="2002-01-01", institution="GSU", course="Chemistry",
            category=Member.Category.UNDERGRADUATE, passport_photo=make_image("p.png"),
        )
        application = RegistrationApplication.objects.create(member=member)
        application.status = RegistrationApplication.Status.APPROVED
        application.save()

        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "Total Registered Members")
        # 1 total member, 1 undergraduate — both appear in the statistics cards.
        self.assertContains(response, ">1<")

    def test_election_status_sections_show_upcoming_active_and_completed(self):
        now = timezone.now()
        upcoming = Election.objects.create(
            association=self.association, name="Upcoming Poll",
            start_datetime=now + datetime.timedelta(days=1), end_datetime=now + datetime.timedelta(days=2),
        )
        active = Election.objects.create(
            association=self.association, name="Active Poll",
            start_datetime=now - datetime.timedelta(hours=1), end_datetime=now + datetime.timedelta(hours=1),
        )
        closed = Election.objects.create(
            association=self.association, name="Closed Poll",
            start_datetime=now - datetime.timedelta(days=2), end_datetime=now - datetime.timedelta(days=1),
        )
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "Upcoming Poll")
        self.assertContains(response, "Active Poll")
        self.assertContains(response, "Closed Poll")

    def test_cta_section_buttons_present(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "Become A Member")
        self.assertContains(response, "Participate In Elections")

    def test_graceful_when_no_association_configured(self):
        Association.objects.all().delete()
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        # Real apostrophe, not an HTML entity — this is literal template
        # text, not a templated variable, so Django's auto-escaping
        # (which only applies to {{ }} output) never touches it.
        self.assertContains(response, "isn't fully configured")


class AboutPageTests(CoreViewsTestCase):
    """PART 7: history, mission, vision, leadership content blocks."""

    def test_about_page_renders_content_blocks(self):
        response = self.client.get(reverse("core:about"))
        self.assertContains(response, "Founded in 2015.")
        self.assertContains(response, "To serve students.")
        self.assertContains(response, "A thriving student body.")

    def test_about_page_shows_placeholder_when_content_missing(self):
        self.site_settings.mission = ""
        self.site_settings.save()
        response = self.client.get(reverse("core:about"))
        self.assertContains(response, "awaiting content")


class ContactPageTests(CoreViewsTestCase):
    """PART 8: contact details, social links, and the contact form -> ContactMessage."""

    def test_get_shows_contact_details(self):
        response = self.client.get(reverse("core:contact"))
        self.assertContains(response, "msa@example.com")
        self.assertContains(response, "08000000000")

    def test_valid_submission_creates_contact_message_and_redirects_with_flash(self):
        response = self.client.post(reverse("core:contact"), {
            "name": "Aisha Bello", "email": "aisha@example.com",
            "subject": "Question", "message": "How do I register?",
        })
        # Checked manually (not via assertRedirects) because assertRedirects
        # follows the redirect itself by default, which would consume the
        # one-shot flash message before our own follow-up GET below sees it.
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("core:contact"))

        self.assertEqual(ContactMessage.objects.count(), 1)
        inquiry = ContactMessage.objects.get()
        self.assertEqual(inquiry.association, self.association)
        self.assertEqual(inquiry.name, "Aisha Bello")

        followup = self.client.get(reverse("core:contact"))
        self.assertContains(followup, "Your message has been sent")

    def test_missing_required_field_does_not_create_message(self):
        response = self.client.post(reverse("core:contact"), {
            "name": "", "email": "aisha@example.com", "subject": "Question", "message": "Hi",
        })
        self.assertEqual(response.status_code, 200)  # re-renders the form, no redirect
        self.assertEqual(ContactMessage.objects.count(), 0)

    def test_invalid_email_rejected(self):
        response = self.client.post(reverse("core:contact"), {
            "name": "Aisha", "email": "not-an-email", "subject": "Question", "message": "Hi",
        })
        self.assertEqual(ContactMessage.objects.count(), 0)
        self.assertContains(response, "valid email")
