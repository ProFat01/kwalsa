"""
apps.core holds the one concept every other app hangs off of:
`Association`. SAMS launches with a single tenant (Malam Sidi Students
Association — MSA) but the brief is explicit that the architecture must
support more associations later, so every other app's models carry an
`association` foreign key from day one rather than bolting multi-tenancy
on after the fact (a far more painful migration).

"Public statistics" (also called out in the brief) is intentionally NOT a
model here: it is *derived* data (member counts, election turnout, etc.)
that already lives in members/elections/analytics. Storing a duplicate
copy in core would just create a second source of truth that can drift.
The public landing page's view reads live from apps.analytics.services
(the same functions the analytics dashboards use) rather than from a
cached snapshot — consistent with that module's own reasoning for why
its dashboards don't read from snapshots either.
"""
from django.db import models
from django.utils.text import slugify


class Association(models.Model):
    """
    A single student association tenant (e.g. "Malam Sidi Students
    Association"). Every membership, election, and analytics record is
    scoped to one Association so the same codebase can serve several
    associations without data ever crossing tenant boundaries.
    """

    name = models.CharField(max_length=255, unique=True)
    short_name = models.CharField(
        max_length=20,
        unique=True,
        help_text="Short code used in membership IDs etc., e.g. 'MSA'.",
    )
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    logo = models.ImageField(upload_to="associations/logos/", blank=True, null=True)
    description = models.TextField(blank=True)
    established_year = models.PositiveSmallIntegerField(blank=True, null=True)
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive associations are hidden from new registrations but their historical data is kept.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Association"
        verbose_name_plural = "Associations"

    def __str__(self):
        return self.short_name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.short_name or self.name)
        super().save(*args, **kwargs)


class SiteSettings(models.Model):
    """
    Per-association public-facing configuration. Kept as a one-to-one
    "settings row" (the standard Django singleton-per-tenant pattern)
    rather than scattering these values across global Django settings,
    so each association can be re-branded entirely from the admin once
    the public site exists.

    Note on "Logo" (listed in the Public Website brief's Site Settings
    fields): there's deliberately no second logo field here —
    `Association.logo` already exists and already means exactly this.
    Adding a duplicate `SiteSettings.logo` would just create two places
    that could disagree about which image is "the" logo.
    """

    association = models.OneToOneField(
        Association, on_delete=models.CASCADE, related_name="site_settings"
    )
    motto = models.CharField(max_length=255, blank=True, help_text='Short tagline shown under the name, e.g. "Unity in Service".')
    welcome_message = models.TextField(blank=True, help_text="Shown in the landing page hero, below the motto.")
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    address = models.CharField(max_length=255, blank=True)
    about_text = models.TextField(blank=True, help_text="Brief history of the association, shown on the About page.")
    mission = models.TextField(blank=True)
    vision = models.TextField(blank=True)
    leadership_text = models.TextField(
        blank=True,
        help_text=(
            "Free-text leadership/executive listing for the About page. Kept as a single "
            "editable block rather than a separate Leadership model for now — easy to "
            "upgrade to per-person profiles with photos later if that's ever needed; "
            "today this is just a content block, like Mission/Vision."
        ),
    )
    donation_details = models.TextField(
        blank=True,
        help_text="Bank name, account name, and account number for donations — free text so it can be formatted however makes sense.",
    )
    hero_image = models.ImageField(upload_to="associations/hero/", blank=True, null=True)
    facebook_url = models.URLField(blank=True)
    x_url = models.URLField(blank=True, verbose_name="X (Twitter) URL")
    instagram_url = models.URLField(blank=True)
    whatsapp_url = models.URLField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Site Settings"
        verbose_name_plural = "Site Settings"

    def __str__(self):
        return f"Site settings — {self.association.short_name}"


class ContactMessage(models.Model):
    """
    An inquiry submitted through the public Contact page. Deliberately
    plain — no status workflow beyond `is_read`, since this is a simple
    "did someone look at this yet" triage tool for site admins, not a
    full ticketing system.
    """

    association = models.ForeignKey(
        Association, on_delete=models.CASCADE, related_name="contact_messages"
    )
    name = models.CharField(max_length=255)
    email = models.EmailField()
    subject = models.CharField(max_length=255)
    message = models.TextField()
    submitted_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ["-submitted_at"]
        verbose_name = "Contact Message"
        verbose_name_plural = "Contact Messages"

    def __str__(self):
        return f"{self.subject} — {self.name}"


class SequenceCounter(models.Model):
    """
    Race-condition-safe counter backing every human-readable, sequential
    identifier in the project (Member.membership_id,
    RegistrationApplication.application_number, and any future one).

    Why a dedicated counter row instead of `Member.objects.count() + 1` or
    `MAX(id)`: both of those re-read a table that other requests are
    concurrently inserting into, which is exactly how two simultaneous
    registrations end up minted with the same membership ID. Locking a
    single small counter row with `select_for_update()` inside an atomic
    transaction (see core/utils.py:get_next_sequence) serialises just the
    increment, not the whole Member table, and is the same pattern already
    proven for certificate ID generation elsewhere.
    """

    association = models.ForeignKey(
        Association, on_delete=models.CASCADE, related_name="sequence_counters"
    )
    key = models.CharField(
        max_length=50,
        help_text="Logical sequence name, e.g. 'membership_id' or 'application_number'.",
    )
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["association", "key"], name="unique_sequence_per_association")
        ]
        verbose_name = "Sequence Counter"
        verbose_name_plural = "Sequence Counters"

    def __str__(self):
        return f"{self.association.short_name}:{self.key} = {self.last_value}"
