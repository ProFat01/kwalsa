# Generated for SAMS v1.1 — Feature 1: optional email field on Member.
# blank=True without null=True: EmailField stores "" for "not provided",
# consistent with Django's text-field convention. Existing rows receive
# the field default of "" automatically — no data migration needed.
# Fully additive: applying this migration while the site is live is safe.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("members", "0003_membership_card_v1"),
    ]

    operations = [
        migrations.AddField(
            model_name="member",
            name="email",
            field=models.EmailField(
                blank=True,
                default="",
                help_text="Optional. Used to send the welcome email when your application is approved.",
                max_length=254,
            ),
            preserve_default=False,
        ),
    ]
