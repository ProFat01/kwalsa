"""
Regression tests for the frontend integration audit (logo, donation
details). Candidate photo display and live results visibility tests
live in apps/elections/tests/ since they depend on Election/Candidate
fixtures.
"""
from django.test import override_settings
from django.urls import reverse

from apps.core.models import Association, SiteSettings
from apps.members.tests.helpers import MediaIsolatedTestCase, make_image


@override_settings(DEFAULT_ASSOCIATION_SLUG="msa")
class LogoDisplayTests(MediaIsolatedTestCase):
    """ISSUE 1: uploaded Association.logo must actually render on the public site."""

    def setUp(self):
        self.association = Association.objects.create(
            name="Malam Sidi Students Association", short_name="MSA", slug="msa"
        )

    def test_logo_renders_on_homepage_when_uploaded(self):
        self.association.logo.save("logo.png", make_image("logo.png"), save=True)
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, self.association.logo.url)
        self.assertContains(response, "brand-logo")

    def test_no_broken_image_tag_when_logo_not_uploaded(self):
        response = self.client.get(reverse("core:home"))
        self.assertNotContains(response, "brand-logo")

    def test_logo_renders_on_every_page_via_shared_base_template(self):
        """The logo lives in base.html's header, so it must appear on every page, not just home."""
        self.association.logo.save("logo.png", make_image("logo.png"), save=True)
        for url in [reverse("core:home"), reverse("core:about"), reverse("core:contact")]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, self.association.logo.url)


@override_settings(DEFAULT_ASSOCIATION_SLUG="msa")
class DonationDisplayTests(MediaIsolatedTestCase):
    """ISSUE 3: SiteSettings.donation_details must display on the recommended locations."""

    def setUp(self):
        self.association = Association.objects.create(
            name="Malam Sidi Students Association", short_name="MSA", slug="msa"
        )
        self.site_settings = SiteSettings.objects.create(
            association=self.association,
            donation_details="Bank: Example Bank\nAccount Name: MSA Fund\nAccount Number: 0123456789",
        )

    def test_donation_details_appear_on_landing_page(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "Example Bank")
        self.assertContains(response, "MSA Fund")

    def test_donation_details_appear_on_about_page(self):
        response = self.client.get(reverse("core:about"))
        self.assertContains(response, "Example Bank")

    def test_donation_details_appear_in_footer_on_any_page(self):
        response = self.client.get(reverse("core:contact"))
        self.assertContains(response, "Support Us")
        self.assertContains(response, "Example Bank")

    def test_donation_section_absent_from_landing_page_when_not_configured(self):
        self.site_settings.donation_details = ""
        self.site_settings.save()
        response = self.client.get(reverse("core:home"))
        self.assertNotContains(response, "Example Bank")
