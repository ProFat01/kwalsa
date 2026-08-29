"""
Regression tests for Module 2: Landing Page Experience.

Django's test client never executes JavaScript, so what's asserted
here is exactly the server-rendered contract the JS depends on: the
correct real numbers/dates/percentages are present in the HTML (not
placeholder zeros), the conditional sections appear/disappear
correctly based on election state, and the CSP-safety invariant (zero
inline style/script) continues to hold on the now much richer home
page. The interactive behaviors themselves (count-up animation,
countdown ticking, conic-gradient pie chart, hero background image)
were verified with a real headless-browser session during development
-- see LANDING_PAGE_EXPERIENCE.md "Verification performed".
"""
import datetime

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Association, ContactMessage, SiteSettings
from apps.elections.models import Candidate, Election, Position, Vote
from apps.members.models import Member, RegistrationApplication
from apps.members.tests.helpers import MediaIsolatedTestCase, make_image


@override_settings(DEFAULT_ASSOCIATION_SLUG="msa")
class LandingPageExperienceTestCase(MediaIsolatedTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.association = Association.objects.create(
            name="Malam Sidi Students Association", short_name="MSA", slug="msa"
        )
        cls.site_settings = SiteSettings.objects.create(
            association=cls.association,
            motto="Unity in Service",
            welcome_message="Welcome.",
            donation_details="Bank: Example Bank\nAccount Name: MSA Fund\nAccount Number: 0123456789",
            contact_email="msa@example.com",
        )
        cls.president = Position.objects.create(association=cls.association, title="President")


class HeroConditionalVoteButtonTests(LandingPageExperienceTestCase):
    """Section 1: the third hero CTA must appear only when an election is active."""

    def test_vote_now_absent_with_no_elections_at_all(self):
        response = self.client.get(reverse("core:home"))
        self.assertNotContains(response, "Vote Now")

    def test_vote_now_absent_when_only_upcoming_election_exists(self):
        now = timezone.now()
        Election.objects.create(
            association=self.association, name="Future Poll",
            start_datetime=now + datetime.timedelta(days=1), end_datetime=now + datetime.timedelta(days=2),
        )
        response = self.client.get(reverse("core:home"))
        self.assertNotContains(response, "Vote Now")

    def test_vote_now_absent_when_only_closed_election_exists(self):
        now = timezone.now()
        Election.objects.create(
            association=self.association, name="Past Poll",
            start_datetime=now - datetime.timedelta(days=2), end_datetime=now - datetime.timedelta(days=1),
        )
        response = self.client.get(reverse("core:home"))
        self.assertNotContains(response, "Vote Now")

    def test_vote_now_present_and_links_to_correct_election_when_active(self):
        now = timezone.now()
        election = Election.objects.create(
            association=self.association, name="Live Poll",
            start_datetime=now - datetime.timedelta(hours=1), end_datetime=now + datetime.timedelta(hours=1),
        )
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "Vote Now")
        self.assertContains(response, reverse("elections:voting_login", args=[election.pk]))

    def test_soonest_closing_active_election_is_spotlighted_when_several_are_active(self):
        now = timezone.now()
        Election.objects.create(
            association=self.association, name="Closes Later",
            start_datetime=now - datetime.timedelta(hours=1), end_datetime=now + datetime.timedelta(days=5),
        )
        soonest = Election.objects.create(
            association=self.association, name="Closes Sooner",
            start_datetime=now - datetime.timedelta(hours=1), end_datetime=now + datetime.timedelta(hours=2),
        )
        response = self.client.get(reverse("core:home"))
        # The hero's Vote Now button and the Spotlight section should both
        # target the soonest-closing election, not just any active one.
        self.assertContains(response, reverse("elections:voting_login", args=[soonest.pk]))
        self.assertContains(response, "Closes Sooner")


class StatisticsCardsTests(LandingPageExperienceTestCase):
    """Section 2: real membership figures, election status, and conditional votes-cast."""

    def _approved_member(self, **overrides):
        defaults = dict(
            association=self.association, full_name="Voter", phone_number="08010000001",
            nin_number="10000000001", date_of_birth="2001-01-01", institution="GSU", course="Chemistry",
            category=Member.Category.UNDERGRADUATE,
        )
        defaults.update(overrides)
        member = Member.objects.create(passport_photo=make_image("p.png"), **defaults)
        application = RegistrationApplication.objects.create(member=member)
        application.status = RegistrationApplication.Status.APPROVED
        application.save()
        member.refresh_from_db()
        return member

    def test_membership_counts_render_as_real_numbers_not_placeholder_zero(self):
        self._approved_member()
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "Total Registered Members")
        # The real count (1) must be present as rendered text -- JS only
        # animates *on top of* this value, it never supplies it.
        self.assertContains(response, '<div class="value record u-countup">1</div>')

    def test_election_status_shows_none_badge_with_no_active_election(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "Election Status")
        self.assertContains(response, '<span class="badge badge-closed">None</span>')

    def test_election_status_shows_active_badge_and_votes_cast_when_active(self):
        now = timezone.now()
        election = Election.objects.create(
            association=self.association, name="Live Poll",
            start_datetime=now - datetime.timedelta(hours=1), end_datetime=now + datetime.timedelta(hours=1),
        )
        election.positions.set([self.president])
        candidate = Candidate.objects.create(election=election, position=self.president, name="A")
        voter = self._approved_member()
        Vote.objects.create(election=election, member=voter, candidate=candidate)

        response = self.client.get(reverse("core:home"))
        self.assertContains(response, '<span class="badge badge-active">Active</span>')
        self.assertContains(response, "Total Votes Cast")


class WhyJoinSectionTests(LandingPageExperienceTestCase):
    """Section 4: new static benefits section."""

    def test_why_join_section_present_with_all_five_benefits(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "Why Join")
        for benefit in [
            "Participate in Elections",
            "Build a Professional Network",
            "Alumni Recognition",
            "Attend Events",
            "Leadership Opportunities",
        ]:
            self.assertContains(response, benefit)


class ActiveElectionSpotlightTests(LandingPageExperienceTestCase):
    """Section 5: spotlight card with countdown, or the exact fallback message."""

    def test_no_active_election_shows_exact_required_message(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "No election is currently active.")

    def test_active_election_shows_name_period_and_countdown_target(self):
        now = timezone.now()
        election = Election.objects.create(
            association=self.association, name="MSA General Election 2026",
            start_datetime=now - datetime.timedelta(hours=1), end_datetime=now + datetime.timedelta(hours=5),
        )
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "MSA General Election 2026")
        self.assertContains(response, "data-countdown-until=")
        self.assertContains(response, reverse("elections:results", args=[election.pk]))


class LiveResultsPreviewTests(LandingPageExperienceTestCase):
    """Section 6: candidate ranking + progress bars + pie chart data, reusing Election.results_by_position() untouched."""

    def setUp(self):
        now = timezone.now()
        self.election = Election.objects.create(
            association=self.association, name="Live Poll",
            start_datetime=now - datetime.timedelta(hours=1), end_datetime=now + datetime.timedelta(hours=1),
        )
        self.election.positions.set([self.president])
        self.candidate_a = Candidate.objects.create(election=self.election, position=self.president, name="Aisha Bello")
        self.candidate_b = Candidate.objects.create(election=self.election, position=self.president, name="Musa Ibrahim")

    def _approved_member(self, phone, nin):
        member = Member.objects.create(
            association=self.association, full_name="Voter", phone_number=phone, nin_number=nin,
            date_of_birth="2001-01-01", institution="GSU", course="Chemistry",
            category=Member.Category.UNDERGRADUATE, passport_photo=make_image("p.png"),
        )
        application = RegistrationApplication.objects.create(member=member)
        application.status = RegistrationApplication.Status.APPROVED
        application.save()
        member.refresh_from_db()
        return member

    def test_preview_shows_honestly_with_zero_votes_when_election_is_active(self):
        """
        The brief's only stated condition for Section 6 is "if an
        election is active" -- not "if votes > 0" -- so a freshly
        opened election with no votes yet correctly still shows the
        section, honestly reporting "0 votes counted so far" rather
        than hiding real, current (if uneventful) information.
        """
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "<h2>Live Results Preview")
        self.assertContains(response, "0 votes counted so far")

    def test_preview_shows_correct_vote_counts_and_percentages(self):
        voter1 = self._approved_member("08010000001", "10000000001")
        voter2 = self._approved_member("08010000002", "10000000002")
        voter3 = self._approved_member("08010000003", "10000000003")
        Vote.objects.create(election=self.election, member=voter1, candidate=self.candidate_a)
        Vote.objects.create(election=self.election, member=voter2, candidate=self.candidate_a)
        Vote.objects.create(election=self.election, member=voter3, candidate=self.candidate_b)

        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "<h2>Live Results Preview")
        self.assertContains(response, "Aisha Bello")
        self.assertContains(response, "Musa Ibrahim")
        # 2 of 3 votes -> 66.7%; these are the exact figures
        # Election.results_by_position() already computes and tests
        # elsewhere (test_results_and_dashboard.py) -- this only checks
        # they reach the home page unchanged.
        self.assertContains(response, "66.7")
        self.assertContains(response, 'data-percentage="66.7"')
        self.assertContains(response, reverse("elections:results", args=[self.election.pk]))

    def test_preview_absent_for_closed_election_even_with_votes(self):
        self.election.start_datetime = timezone.now() - datetime.timedelta(days=2)
        self.election.end_datetime = timezone.now() - datetime.timedelta(days=1)
        self.election.save()
        voter = self._approved_member("08010000001", "10000000001")
        Vote.objects.create(election=self.election, member=voter, candidate=self.candidate_a)

        response = self.client.get(reverse("core:home"))
        # Checked against the actual rendered heading tag, not the bare
        # phrase -- this template's own "<!-- SECTION 6: Live Results
        # Preview -->" boundary comment contains that same phrase, so a
        # plain substring match would false-positive against the comment
        # even when the real section is correctly absent.
        self.assertNotContains(response, "<h2>Live Results Preview")


class DonationSectionTests(LandingPageExperienceTestCase):
    """Section 7: donation info from Site Settings, only when present."""

    def test_donation_section_shown_with_anchor_when_configured(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, 'id="donate"')
        self.assertContains(response, "Example Bank")

    def test_donation_section_absent_when_not_configured(self):
        self.site_settings.donation_details = ""
        self.site_settings.save()
        response = self.client.get(reverse("core:home"))
        self.assertNotContains(response, 'id="donate"')

    def test_footer_donate_link_only_appears_when_donation_configured(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, 'href="/#donate"')

        self.site_settings.donation_details = ""
        self.site_settings.save()
        response = self.client.get(reverse("core:home"))
        self.assertNotContains(response, 'href="/#donate"')


class EmbeddedContactSectionTests(LandingPageExperienceTestCase):
    """Section 8: mini contact form embedded on the landing page, posting to the unmodified contact_view."""

    def test_contact_section_renders_details_and_form_fields(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "msa@example.com")
        self.assertContains(response, '<form method="post" action="' + reverse("core:contact") + '"')
        self.assertContains(response, 'name="name"')
        self.assertContains(response, 'name="email"')
        self.assertContains(response, 'name="subject"')
        self.assertContains(response, 'name="message"')

    def test_submitting_the_embedded_form_creates_a_contact_message(self):
        """
        Proves the embedded form genuinely reuses contact_view unchanged
        -- it posts to core:contact, the exact same endpoint the
        standalone /contact/ page uses, with zero new view code.
        """
        response = self.client.post(reverse("core:contact"), {
            "name": "Aisha Bello", "email": "aisha@example.com",
            "subject": "Question from homepage", "message": "Submitted via the embedded landing-page form.",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ContactMessage.objects.count(), 1)
        self.assertEqual(ContactMessage.objects.get().subject, "Question from homepage")


class FooterLogoTests(LandingPageExperienceTestCase):
    """Section 9: association logo in the footer."""

    def test_footer_shows_logo_when_uploaded(self):
        self.association.logo.save("logo.png", make_image("logo.png"), save=True)
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, 'class="footer-logo"')
        self.assertContains(response, self.association.logo.url)

    def test_footer_omits_logo_img_when_not_uploaded(self):
        response = self.client.get(reverse("core:home"))
        self.assertNotContains(response, 'class="footer-logo"')


class LandingPageCspSafetyTests(LandingPageExperienceTestCase):
    """
    The landing page grew substantially in this module (hero background
    image, countdown, pie chart, count-up numbers) -- re-confirms the
    CSP-safety invariant specifically against the richer page, in
    addition to the general sweep in test_design_system.py.
    """

    def test_no_inline_style_or_script_even_with_every_optional_section_populated(self):
        self.association.logo.save("logo.png", make_image("logo.png"), save=True)
        self.site_settings.hero_image.save("hero.png", make_image("hero.png"), save=True)
        now = timezone.now()
        election = Election.objects.create(
            association=self.association, name="Live Poll",
            start_datetime=now - datetime.timedelta(hours=1), end_datetime=now + datetime.timedelta(hours=1),
        )
        election.positions.set([self.president])
        candidate = Candidate.objects.create(election=election, position=self.president, name="A")
        voter = Member.objects.create(
            association=self.association, full_name="Voter", phone_number="08010000001",
            nin_number="10000000001", date_of_birth="2001-01-01", institution="GSU", course="Chemistry",
            category=Member.Category.UNDERGRADUATE, passport_photo=make_image("p.png"),
        )
        application = RegistrationApplication.objects.create(member=voter)
        application.status = RegistrationApplication.Status.APPROVED
        application.save()
        voter.refresh_from_db()
        Vote.objects.create(election=election, member=voter, candidate=candidate)

        response = self.client.get(reverse("core:home"))
        self.assertNotIn(b'style="', response.content)
        self.assertNotIn(b"<script>", response.content)
        self.assertContains(response, '<script src="/static/js/home.js"')

    def test_hero_uses_data_attribute_not_inline_style_for_background_image(self):
        self.site_settings.hero_image.save("hero.png", make_image("hero.png"), save=True)
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "data-hero-bg=")
        self.assertNotIn(b'style="', response.content)
