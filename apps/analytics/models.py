"""
apps.analytics deliberately stores *precomputed snapshots* rather than
recomputing aggregates from Member/Vote on every dashboard request.

Why: membership counts and turnout percentages are exactly the kind of
GROUP BY/COUNT queries that get expensive as Member/Vote grow, and a
public statistics page (core's stated requirement) hitting those live on
every page load doesn't scale. Snapshots are written by a periodic
management command (or signal, for election results) and read cheaply by
whatever dashboard/chart UI comes in a later phase. Age in particular is
*only* meaningful as of a point in time — storing a live "age" column on
Member would go stale the moment it's read — so it's computed from
date_of_birth at snapshot time and bucketed here, never stored on Member.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import Association
from apps.elections.models import Candidate, Election


class PageVisit(models.Model):
    """
    v2.1 — Visitor & Usage Analytics (see VISITOR_ANALYTICS.md for the
    full design writeup). One compact row per meaningful public page
    view — a single INSERT per tracked request, nothing more.

    Deliberately NOT a raw-IP / raw-request log:
      - `visitor_hash` is a one-way HMAC-SHA256 of (IP, User-Agent,
        association, calendar day) using a server-side secret
        (settings.SECRET_KEY, or VISITOR_HASH_SALT if set) — never the
        raw IP. The calendar day is baked into the hash itself (not a
        separate stored field) specifically so the same visitor gets a
        *different* hash on different days: this is what makes
        "unique visitors" a privacy-preserving approximation rather
        than a persistent cross-day tracking ID (see
        apps.analytics.tracking.hash_visitor). A consequence is that
        weekly/monthly "unique visitors" are really "unique
        visitor-days" summed across the range — documented in the
        dashboard and in VISITOR_ANALYTICS.md, not hidden.
      - `path` stores Django's resolved URL name ("core:home",        "elections:election_detail", ...), never the raw querystring
        or POST body, so dynamic paths like /elections/3/ and
        /elections/7/ aggregate under one "Elections" row instead of
        fragmenting "most visited pages" by primary key.
      - device/browser/referrer are broad categories, not full
        User-Agent/Referer strings — no fingerprint-grade detail is
        retained.

    `visit_date` is a plain DateField (not derived from `visited_at` at
    query time) purely so every dashboard/retention query can filter on
    an indexed field directly instead of a __date lookup on a
    DateTimeField, which SQLite cannot use an index for.
    """

    class VisitorType(models.TextChoices):
        ANONYMOUS = "anonymous", "Anonymous"
        MEMBER = "member", "Authenticated Member"

    class DeviceCategory(models.TextChoices):
        MOBILE = "mobile", "Mobile"
        DESKTOP = "desktop", "Desktop"
        TABLET = "tablet", "Tablet"
        UNKNOWN = "unknown", "Unknown"

    class BrowserCategory(models.TextChoices):
        CHROME = "chrome", "Chrome"
        FIREFOX = "firefox", "Firefox"
        EDGE = "edge", "Edge"
        SAFARI = "safari", "Safari"
        OTHER = "other", "Other"

    class ReferrerCategory(models.TextChoices):
        DIRECT = "direct", "Direct"
        SEARCH = "search", "Search Engine"
        SOCIAL = "social", "Social Media"
        OTHER_WEBSITE = "other_website", "Other Website"
        UNKNOWN = "unknown", "Unknown"

    association = models.ForeignKey(
        Association, on_delete=models.CASCADE, related_name="page_visits", null=True, blank=True,
        help_text="Null if no association is configured yet at request time.",
    )
    visit_date = models.DateField(help_text="Calendar date of the visit, for indexed date-range filtering.")
    visited_at = models.DateTimeField(auto_now_add=True)
    page_key = models.CharField(
        max_length=100,
        help_text="Resolved URL name (e.g. 'core:home', 'elections:election_detail'), not the raw path.",
    )
    path = models.CharField(max_length=255, help_text="Raw request path, for reference only.")
    visitor_hash = models.CharField(
        max_length=64, help_text="One-way HMAC of IP+User-Agent+day. Never the raw IP.",
    )
    visitor_type = models.CharField(max_length=10, choices=VisitorType.choices, default=VisitorType.ANONYMOUS)
    device_category = models.CharField(max_length=10, choices=DeviceCategory.choices, default=DeviceCategory.UNKNOWN)
    browser_category = models.CharField(max_length=10, choices=BrowserCategory.choices, default=BrowserCategory.OTHER)
    referrer_category = models.CharField(
        max_length=15, choices=ReferrerCategory.choices, default=ReferrerCategory.UNKNOWN
    )

    class Meta:
        indexes = [
            # Retention cleanup: no association filter, all rows by age.
            models.Index(fields=["visit_date"], name="pv_visit_date_idx"),
            # Every dashboard query filters (association, visit_date range)
            # together (see querysets.page_visits_for_range) — this is the
            # composite that actually gets chosen by the query planner over
            # the FK's own single-column index; verified with EXPLAIN QUERY
            # PLAN at 10k rows, see VISITOR_ANALYTICS.md "Performance".
            models.Index(fields=["association", "visit_date"], name="pv_assoc_date_idx"),
            # "Most visited pages" for a date range.
            models.Index(fields=["association", "visit_date", "page_key"], name="pv_assoc_date_page_idx"),
            # Device / browser / referrer breakdowns for a date range.
            models.Index(
                fields=["association", "visit_date", "device_category"], name="pv_assoc_date_device_idx"
            ),
            models.Index(
                fields=["association", "visit_date", "browser_category"], name="pv_assoc_date_browser_idx"
            ),
            models.Index(
                fields=["association", "visit_date", "referrer_category"], name="pv_assoc_date_referrer_idx"
            ),
        ]
        permissions = [
            ("view_visitor_analytics", "Can view the visitor analytics dashboard"),
        ]
        verbose_name = "Page Visit"
        verbose_name_plural = "Page Visits"

    def __str__(self):
        return f"{self.page_key} @ {self.visit_date}"


class MembershipSnapshot(models.Model):
    association = models.ForeignKey(
        Association, on_delete=models.CASCADE, related_name="membership_snapshots"
    )
    snapshot_date = models.DateField()
    total_members = models.PositiveIntegerField(default=0)
    total_approved = models.PositiveIntegerField(default=0)
    total_pending = models.PositiveIntegerField(default=0)
    total_rejected = models.PositiveIntegerField(default=0)
    total_alumni = models.PositiveIntegerField(default=0)
    total_undergraduate = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-snapshot_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["association", "snapshot_date"], name="unique_membership_snapshot_per_day"
            )
        ]
        permissions = [
            ("view_analytics_dashboard", "Can view the analytics dashboard"),
        ]
        verbose_name = "Membership Snapshot"
        verbose_name_plural = "Membership Snapshots"

    def __str__(self):
        return f"{self.association.short_name} membership @ {self.snapshot_date}"


class AgeDistributionSnapshot(models.Model):
    class AgeBracket(models.TextChoices):
        # Boundaries per the Analytics Module spec. These supersede the
        # placeholder boundaries this model originally shipped with
        # (under_18/18_20/21_23/24_26/27_plus) — that version was never
        # populated or read anywhere yet, so changing the boundaries now
        # costs nothing and there's no stale data shaped around the old
        # buckets to migrate.
        BELOW_16 = "below_16", "Below 16"
        AGE_16_20 = "16_20", "16–20"
        AGE_21_25 = "21_25", "21–25"
        AGE_26_30 = "26_30", "26–30"
        AGE_31_40 = "31_40", "31–40"
        AGE_41_PLUS = "41_plus", "41+"

    association = models.ForeignKey(
        Association, on_delete=models.CASCADE, related_name="age_distribution_snapshots"
    )
    snapshot_date = models.DateField()
    age_bracket = models.CharField(max_length=10, choices=AgeBracket.choices)
    count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["snapshot_date", "age_bracket"]
        constraints = [
            models.UniqueConstraint(
                fields=["association", "snapshot_date", "age_bracket"],
                name="unique_age_bracket_snapshot_per_day",
            )
        ]
        verbose_name = "Age Distribution Snapshot"
        verbose_name_plural = "Age Distribution Snapshots"

    def __str__(self):
        return f"{self.association.short_name} {self.get_age_bracket_display()} @ {self.snapshot_date}"

    @staticmethod
    def bucket_for_age(age: int) -> str:
        """
        Single source of truth for the age->bracket boundaries, shared by
        snapshot generation (apps.analytics.services) and the live
        (non-snapshotted) age_distribution() computation, so the two can
        never quietly disagree about where one bracket ends and the next
        begins.
        """
        if age < 16:
            return AgeDistributionSnapshot.AgeBracket.BELOW_16
        if age <= 20:
            return AgeDistributionSnapshot.AgeBracket.AGE_16_20
        if age <= 25:
            return AgeDistributionSnapshot.AgeBracket.AGE_21_25
        if age <= 30:
            return AgeDistributionSnapshot.AgeBracket.AGE_26_30
        if age <= 40:
            return AgeDistributionSnapshot.AgeBracket.AGE_31_40
        return AgeDistributionSnapshot.AgeBracket.AGE_41_PLUS


class ElectionResultSnapshot(models.Model):
    """
    One row per (Election, Position), generated once voting closes —
    NOT one row per Election. Now that a single Election can contest
    several Positions at once, "the winner" and "turnout" are only
    meaningful per office (an election has a President winner AND a
    separate Secretary winner; a member might vote for President but
    abstain on Secretary, so turnout genuinely differs by position too).
    Kept separate from Vote (which stays the raw, unaggregated record) so
    results are answered by reading one small row per position instead of
    re-aggregating every Vote on every page view — and so publishing
    results is an explicit, audited action (`is_published`) rather than
    results being implicitly visible the instant the polls close.
    """

    election = models.ForeignKey(Election, on_delete=models.CASCADE, related_name="result_snapshots")
    position = models.ForeignKey("elections.Position", on_delete=models.CASCADE, related_name="result_snapshots")
    total_votes_cast = models.PositiveIntegerField(
        default=0, help_text="Votes cast for this position within this election."
    )
    total_eligible_voters = models.PositiveIntegerField(
        default=0, help_text="Eligible (voting_status=True) members at snapshot time — same across positions in one election."
    )
    turnout_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    winner_candidate = models.ForeignKey(
        Candidate, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    is_published = models.BooleanField(
        default=False, help_text="Gates public visibility once the public results page exists."
    )
    generated_at = models.DateTimeField(auto_now=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="published_results",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["election", "position"], name="unique_result_snapshot_per_position")
        ]
        ordering = ["election", "position__display_order"]
        verbose_name = "Election Result Snapshot"
        verbose_name_plural = "Election Result Snapshots"

    def __str__(self):
        return f"Results — {self.election.name} / {self.position}"

    def clean(self):
        if (
            self.winner_candidate_id
            and self.position_id
            and self.winner_candidate.position_id != self.position_id
        ):
            raise ValidationError({"winner_candidate": "Winner must be a candidate for this snapshot's position."})
