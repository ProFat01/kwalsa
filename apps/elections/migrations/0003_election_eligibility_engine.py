# Generated for Version 2.0 — Advanced Election Eligibility Engine
#
# Purely additive: every new field is nullable/blank with a
# backward-compatible default (scope="national", approved_members_only=
# True, every filter blank/unset), so no existing Election row changes
# meaning and no data is touched or lost.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('elections', '0002_rename_is_active_election_is_enabled_and_more'),
        ('members', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='election',
            name='scope',
            field=models.CharField(
                choices=[
                    ('national', 'National'),
                    ('institution', 'Institution'),
                    ('faculty', 'Faculty'),
                    ('department', 'Department'),
                    ('custom', 'Custom'),
                ],
                default='national',
                help_text='Determines which eligibility filters apply. Existing elections default to National.',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='election',
            name='eligibility_institution',
            field=models.CharField(
                blank=True,
                help_text='Only members of this institution are eligible. Leave blank for no institution restriction.',
                max_length=255,
                verbose_name='Institution',
            ),
        ),
        migrations.AddField(
            model_name='election',
            name='eligibility_faculty',
            field=models.CharField(
                blank=True,
                help_text='Requires Institution to also be set.',
                max_length=255,
                verbose_name='Faculty',
            ),
        ),
        migrations.AddField(
            model_name='election',
            name='eligibility_department',
            field=models.CharField(
                blank=True,
                help_text='Requires Faculty to also be set.',
                max_length=255,
                verbose_name='Department',
            ),
        ),
        migrations.AddField(
            model_name='election',
            name='eligibility_level',
            field=models.CharField(
                blank=True,
                help_text="e.g. '100', 'ND1', 'Year 3' — matched against Member.level.",
                max_length=20,
                verbose_name='Level',
            ),
        ),
        migrations.AddField(
            model_name='election',
            name='eligibility_gender',
            field=models.CharField(
                blank=True,
                choices=[('male', 'Male'), ('female', 'Female')],
                max_length=10,
                verbose_name='Gender',
            ),
        ),
        migrations.AddField(
            model_name='election',
            name='eligibility_membership_category',
            field=models.CharField(
                blank=True,
                choices=[('undergraduate', 'Undergraduate'), ('graduate_alumni', 'Graduate/Alumni')],
                help_text="Applies even for National elections (e.g. 'Undergraduate only').",
                max_length=20,
                verbose_name='Membership Category',
            ),
        ),
        migrations.AddField(
            model_name='election',
            name='approved_members_only',
            field=models.BooleanField(
                default=True,
                help_text='When on (default), only members who are Approved and currently eligible to vote are considered.',
                verbose_name='Approved members only',
            ),
        ),
    ]
