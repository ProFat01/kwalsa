from django.test import TestCase

from apps.core.models import Association, ContactMessage, SiteSettings


class SiteSettingsContentFieldsTests(TestCase):
    """PART 9: editable content fields the public website reads from."""

    def test_new_content_fields_save_and_round_trip(self):
        association = Association.objects.create(name="Malam Sidi Students Association", short_name="MSA")
        settings_obj = SiteSettings.objects.create(
            association=association,
            motto="Unity in Service",
            welcome_message="Welcome to MSA.",
            mission="To serve students.",
            vision="A thriving student body.",
            leadership_text="President: Jane Doe.",
            donation_details="Bank: Example Bank, Acct: 0123456789",
        )
        settings_obj.refresh_from_db()
        self.assertEqual(settings_obj.motto, "Unity in Service")
        self.assertEqual(settings_obj.welcome_message, "Welcome to MSA.")
        self.assertEqual(settings_obj.mission, "To serve students.")
        self.assertEqual(settings_obj.vision, "A thriving student body.")
        self.assertEqual(settings_obj.leadership_text, "President: Jane Doe.")
        self.assertIn("Example Bank", settings_obj.donation_details)

    def test_does_not_duplicate_association_logo(self):
        """PART 9 lists 'Logo' under Site Settings — Association.logo already covers this; SiteSettings has no second logo field."""
        self.assertFalse(hasattr(SiteSettings, "logo"))


class ContactMessageTests(TestCase):
    def setUp(self):
        self.association = Association.objects.create(name="Malam Sidi Students Association", short_name="MSA")

    def test_create_and_default_unread(self):
        message = ContactMessage.objects.create(
            association=self.association, name="Aisha", email="aisha@example.com",
            subject="Question about registration", message="How do I register?",
        )
        self.assertFalse(message.is_read)
        self.assertIsNotNone(message.submitted_at)
        self.assertEqual(str(message), "Question about registration — Aisha")

    def test_ordered_most_recent_first(self):
        first = ContactMessage.objects.create(
            association=self.association, name="A", email="a@example.com", subject="First", message="..."
        )
        second = ContactMessage.objects.create(
            association=self.association, name="B", email="b@example.com", subject="Second", message="..."
        )
        self.assertEqual(list(ContactMessage.objects.all()), [second, first])
