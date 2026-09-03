import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_sitesettings_aims_sitesettings_membership_info_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Leadership',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('full_name', models.CharField(max_length=255)),
                ('position', models.CharField(help_text='e.g. President, Financial Secretary.', max_length=255)),
                ('photo', models.ImageField(blank=True, null=True, upload_to='associations/leadership/%Y/%m/')),
                ('facebook_url', models.URLField(blank=True, help_text="Link to this leader's Facebook profile or page, if available.")),
                ('display_order', models.PositiveSmallIntegerField(default=0, help_text='Controls ordering on the public Leadership page, lowest first.')),
                ('is_active', models.BooleanField(default=True, help_text='Only active leaders are shown on the public Leadership page.')),
                ('association', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='leaders', to='core.association')),
            ],
            options={
                'verbose_name': 'Leader',
                'verbose_name_plural': 'Leadership',
                'ordering': ['display_order', 'full_name'],
            },
        ),
    ]
