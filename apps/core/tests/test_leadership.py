from django.test import override_settings
from django.urls import reverse

from apps.core.models import Association, Leadership, SiteSettings
from apps.members.tests.helpers import MediaIsolatedTestCase, make_image


@override_settings(DEFAULT_ASSOCIATION_SLUG="msa")
class LeadershipPageTestCase(MediaIsolatedTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.association = Association.objects.create(
            name="Malam Sidi Students Association", short_name="MSA", slug="msa"
        )
        SiteSettings.objects.create(association=cls.association)
        cls.other_association = Association.objects.create(
            name="Kwami Local Government Students Association", short_name="KWALSA", slug="kwalsa"
        )


class LeadershipPageRenderTests(LeadershipPageTestCase):
    def test_leadership_page_url_works(self):
        response = self.client.get(reverse("core:leadership"))
        self.assertEqual(response.status_code, 200)

    def test_leadership_page_renders_successfully(self):
        response = self.client.get(reverse("core:leadership"))
        self.assertTemplateUsed(response, "core/leadership.html")


class LeadershipScopingTests(LeadershipPageTestCase):
    def test_active_association_leaders_are_displayed(self):
        Leadership.objects.create(
            association=self.association, full_name="Amina Yusuf", position="President",
        )
        response = self.client.get(reverse("core:leadership"))
        self.assertContains(response, "Amina Yusuf")
        self.assertContains(response, "President")

    def test_leaders_from_another_association_are_not_displayed(self):
        Leadership.objects.create(
            association=self.other_association, full_name="Bello Musa", position="President",
        )
        response = self.client.get(reverse("core:leadership"))
        self.assertNotContains(response, "Bello Musa")

    def test_inactive_leaders_are_not_displayed(self):
        Leadership.objects.create(
            association=self.association, full_name="Chidi Okafor", position="Secretary",
            is_active=False,
        )
        response = self.client.get(reverse("core:leadership"))
        self.assertNotContains(response, "Chidi Okafor")


class LeadershipOrderingTests(LeadershipPageTestCase):
    def test_leaders_are_ordered_by_display_order(self):
        Leadership.objects.create(
            association=self.association, full_name="Second Leader", position="Secretary",
            display_order=2,
        )
        Leadership.objects.create(
            association=self.association, full_name="First Leader", position="President",
            display_order=1,
        )
        response = self.client.get(reverse("core:leadership"))
        content = response.content.decode()
        self.assertLess(content.index("First Leader"), content.index("Second Leader"))


class LeadershipEmptyStateTests(LeadershipPageTestCase):
    def test_empty_state_shown_when_no_leaders(self):
        response = self.client.get(reverse("core:leadership"))
        self.assertContains(response, "will be available soon")

    def test_empty_state_not_shown_when_leaders_exist(self):
        Leadership.objects.create(
            association=self.association, full_name="Amina Yusuf", position="President",
        )
        response = self.client.get(reverse("core:leadership"))
        self.assertNotContains(response, "will be available soon")


class LeadershipPhotoAndFacebookTests(LeadershipPageTestCase):
    def test_page_does_not_break_without_a_photo(self):
        Leadership.objects.create(
            association=self.association, full_name="Amina Yusuf", position="President",
        )
        response = self.client.get(reverse("core:leadership"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "leadership-photo-placeholder")

    def test_photo_renders_when_present(self):
        Leadership.objects.create(
            association=self.association, full_name="Amina Yusuf", position="President",
            photo=make_image("amina.png"),
        )
        response = self.client.get(reverse("core:leadership"))
        self.assertContains(response, "leadership-photo")
        self.assertNotContains(response, "leadership-photo-placeholder")

    def test_facebook_link_shown_when_available(self):
        Leadership.objects.create(
            association=self.association, full_name="Amina Yusuf", position="President",
            facebook_url="https://facebook.com/amina.yusuf",
        )
        response = self.client.get(reverse("core:leadership"))
        self.assertContains(response, "https://facebook.com/amina.yusuf")

    def test_facebook_link_hidden_when_not_available(self):
        Leadership.objects.create(
            association=self.association, full_name="Amina Yusuf", position="President",
        )
        response = self.client.get(reverse("core:leadership"))
        self.assertNotContains(response, "leadership-social")


class LeadershipModelTests(LeadershipPageTestCase):
    def test_string_representation(self):
        leader = Leadership.objects.create(
            association=self.association, full_name="Amina Yusuf", position="President",
        )
        self.assertEqual(str(leader), "Amina Yusuf — President (MSA)")
