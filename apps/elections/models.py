"""
apps.elections.

Ballot structure: one Election explicitly declares which Positions it
contests (`Election.positions`, a M2M to Position), each Position can
have multiple Candidates within that election, and a Vote is cast for one
candidate within one position. The integrity guarantee — "an approved
member can vote at most once per position, during the election's voting
window" — is enforced at the database level via a UniqueConstraint on
(election, member, position) on Vote, not just in application code.

(Earlier iteration note, kept for history: the very first version of
this app modeled "one vote per election" with no position field at all,
i.e. one Election = one single contested office. That was flagged at the
time as the wrong shape for a combined multi-position ballot and has now
been superseded by the design below.)
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.models import Association
from apps.members.models import Member


class Position(models.Model):
    """
    A contestable office (President, General Secretary, ...), normalized
    out of free-text so the same position can be compared/reported on
    consistently across multiple elections and associations — a plain
    CharField on Candidate would let "President", "president", and
    "Pres." all exist as different strings and quietly break analytics.

    Positions belong to an Association, not to a single Election, so the
    same "President" position can be reused election after election
    (clean year-over-year reporting) — which Elections actually contest
    a given Position is recorded on Election.positions below.
    """

    association = models.ForeignKey(
        Association, on_delete=models.CASCADE, related_name="positions"
    )
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    display_order = models.PositiveSmallIntegerField(
        default=0, help_text="Controls ordering on ballots/results, lowest first."
    )

    class Meta:
        ordering = ["display_order", "title"]
        constraints = [
            models.UniqueConstraint(fields=["association", "title"], name="unique_position_per_association")
        ]
        verbose_name = "Position"
        verbose_name_plural = "Positions"

    def __str__(self):
        return self.title


class Election(models.Model):
    class Scope(models.TextChoices):
        """
        What level of the organisation this election is held at. This is
        primarily a UX hint — it drives which eligibility filters the
        admin form shows (see apps/elections/admin.py) and is what the
        validation rules below key off — but the filters themselves
        (below) are what the eligibility engine actually evaluates.
        "Level Representative" and "Female Representative" style
        elections are expressed as Scope.CUSTOM with just the relevant
        filter(s) set, rather than as their own scope values, so adding
        a new kind of representative election never requires a schema
        change — only a different combination of the filters below.
        """

        NATIONAL = "national", "National"
        INSTITUTION = "institution", "Institution"
        FACULTY = "faculty", "Faculty"
        DEPARTMENT = "department", "Department"
        CUSTOM = "custom", "Custom"

    association = models.ForeignKey(
        Association, on_delete=models.PROTECT, related_name="elections"
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    # --- Version 2.0: Election Eligibility Engine ------------------------
    # Every field below is nullable/blank with a backward-compatible
    # default, and an unset filter is simply never applied (see
    # apps/elections/eligibility.py) — so every election that existed
    # before this version automatically keeps behaving exactly as it did:
    # scope defaults to National, approved_members_only defaults to True,
    # and every other filter defaults to "not set" = "no restriction".
    # This is a UI/validation aid; eligibility.py is the actual source of
    # truth and does not care what scope was chosen, only which filters
    # are non-blank.
    scope = models.CharField(
        max_length=20,
        choices=Scope.choices,
        default=Scope.NATIONAL,
        help_text="Determines which eligibility filters apply. Existing elections default to National.",
    )
    eligibility_institution = models.CharField(
        max_length=255, blank=True, verbose_name="Institution",
        help_text="Only members of this institution are eligible. Leave blank for no institution restriction.",
    )
    eligibility_faculty = models.CharField(
        max_length=255, blank=True, verbose_name="Faculty",
        help_text="Requires Institution to also be set.",
    )
    eligibility_department = models.CharField(
        max_length=255, blank=True, verbose_name="Department",
        help_text="Requires Faculty to also be set.",
    )
    eligibility_level = models.CharField(
        max_length=20, blank=True, verbose_name="Level",
        help_text="e.g. '100', 'ND1', 'Year 3' — matched against Member.level.",
    )
    eligibility_gender = models.CharField(
        max_length=10, choices=Member.Gender.choices, blank=True, verbose_name="Gender",
    )
    # Reuses Member.Category (Undergraduate / Graduate-Alumni) rather than
    # introducing a second, duplicate "membership category" concept — see
    # PROJECT BACKGROUND: "If this field already exists, reuse it."
    eligibility_membership_category = models.CharField(
        max_length=20, choices=Member.Category.choices, blank=True, verbose_name="Membership Category",
        help_text="Applies even for National elections (e.g. 'Undergraduate only').",
    )
    approved_members_only = models.BooleanField(
        default=True,
        verbose_name="Approved members only",
        help_text="When on (default), only members who are Approved and currently eligible to vote are considered.",
    )
    # The explicit "contains multiple positions" relationship: defines the
    # ballot structure (which offices are being contested) independently
    # of candidates being nominated yet. Candidate.clean() below requires
    # a candidate's position to be one of these, so the ballot shape is
    # decided first and candidates are added against it — not inferred
    # after the fact from whatever candidates happen to exist.
    positions = models.ManyToManyField(
        Position,
        related_name="elections",
        blank=True,
        help_text="Positions being contested in this election. Add these before adding candidates.",
    )
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()
    # Admin-controlled switch, independent of the clock: lets staff publish
    # an election (visible, candidates locked in) ahead of its voting
    # window, or pull one down in an emergency, without touching the
    # start/end timestamps. Whether voting is *actually* open right now is
    # always computed from the clock (see is_active()/is_voting_open
    # below), never this flag alone.
    #
    # Named `is_enabled` rather than `is_active` specifically because the
    # election-module spec requires a method called `is_active()` that
    # means something different (currently between start_datetime and
    # end_datetime) — Python won't let a field and a method share one
    # name on the same class, so one of the two had to be renamed. This
    # field keeps its exact original behaviour, just under a name that
    # doesn't collide; nothing about what it *does* changed.
    is_enabled = models.BooleanField(
        default=True, help_text="Whether this election is published/enabled at all."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_elections",
    )

    class Meta:
        ordering = ["-start_datetime"]
        permissions = [
            ("manage_election", "Can create, edit, or activate/deactivate elections"),
            ("publish_results", "Can publish election results"),
        ]
        verbose_name = "Election"
        verbose_name_plural = "Elections"

    def __str__(self):
        return self.name

    def clean(self):
        if self.start_datetime and self.end_datetime and self.end_datetime <= self.start_datetime:
            raise ValidationError({"end_datetime": "End time must be after the start time."})

        # Eligibility filter validation. National elections ignore every
        # location filter (see eligibility.py), so there is nothing to
        # validate for them even if stray values are present.
        if self.scope != self.Scope.NATIONAL:
            if self.eligibility_department and not self.eligibility_faculty:
                raise ValidationError(
                    {"eligibility_faculty": "Faculty is required when Department is set."}
                )
            if self.eligibility_faculty and not self.eligibility_institution:
                raise ValidationError(
                    {"eligibility_institution": "Institution is required when Faculty is set."}
                )

    # --- Status: computed on every access, never stored. ---------------
    # Storing a "status" column that has to be kept in sync with the clock
    # is exactly the kind of staleness this project avoids elsewhere (see
    # analytics.AgeDistributionSnapshot's reasoning for the same call on
    # age). Computing it fresh on every access is what "status should
    # update automatically" means here: there is no cron job, no signal,
    # and nothing that can fall out of sync, because nothing is ever
    # cached in the first place.
    def is_upcoming(self) -> bool:
        return timezone.now() < self.start_datetime

    def is_active(self) -> bool:
        """Between start and end, by the clock alone — independent of is_enabled."""
        now = timezone.now()
        return self.start_datetime <= now <= self.end_datetime

    def is_closed(self) -> bool:
        return timezone.now() > self.end_datetime

    @property
    def status(self) -> str:
        """One of "upcoming" / "active" / "closed" — for display in templates/admin."""
        if self.is_upcoming():
            return "upcoming"
        if self.is_closed():
            return "closed"
        return "active"

    @property
    def is_voting_open(self) -> bool:
        """
        The single source of truth for "can a member actually vote right
        now" — combines the admin's publish/enable switch with the pure
        clock-based is_active() check above. Use this (not is_active()
        alone) anywhere voting eligibility is being decided; is_active()
        alone answers a narrower question ("are we inside the time
        window") that an admin can still override by disabling the
        election.
        """
        return bool(self.is_enabled and self.is_active())

    # --- Voting / results helpers, all computed live. -------------------
    def has_member_voted(self, member) -> bool:
        return self.votes.filter(member=member).exists()

    def eligible_members(self):
        """
        QuerySet of every Member eligible to vote in this election, per
        the Election Eligibility Engine (apps/elections/eligibility.py).
        The engine — not this method — is the single source of truth;
        this is just the convenient access point every other module
        (voting views, analytics, admin) should call through.
        """
        from .eligibility import eligible_members as _eligible_members

        return _eligible_members(self)

    def is_member_eligible(self, member) -> bool:
        """Whether `member` may vote in this specific election. See eligibility.py."""
        from .eligibility import is_member_eligible as _is_member_eligible

        return _is_member_eligible(member, self)

    def eligible_voters_count(self) -> int:
        """
        Count of members currently eligible to vote in this election.
        Pre-2.0 this only ever meant "voting_status=True members of the
        association" (equivalent to a National election with default
        filters) — eligible_members() reduces to exactly that query when
        no eligibility filters are set, so every existing election keeps
        the same count it always had.
        """
        return self.eligible_members().count()

    def voters_count(self) -> int:
        """Distinct members who have cast at least one vote — i.e. ballots submitted, not Vote rows."""
        return self.votes.values("member_id").distinct().count()

    def turnout_percentage(self, eligible=None, voters=None) -> float:
        """
        `eligible`/`voters` let a caller that has already computed
        eligible_voters_count()/voters_count() (e.g. to display them
        separately alongside turnout, as every dashboard in this project
        does) pass those numbers straight through instead of this method
        silently re-running both queries. Purely an optimization — with
        no arguments this computes both itself exactly as before, so
        every existing caller keeps working unchanged.
        """
        eligible = self.eligible_voters_count() if eligible is None else eligible
        if not eligible:
            return 0.0
        voters = self.voters_count() if voters is None else voters
        return round(voters / eligible * 100, 1)

    def results_by_position(self):
        """
        Live vote tally for every contested position: each candidate's
        vote count and share-of-vote percentage (of votes cast *for that
        position*, the standard election-results meaning — not of total
        eligible voters, which is what turnout_percentage() answers
        instead). Computed fresh from Vote on every call — no caching, no
        snapshot table, deliberately (see PART 8 in ELECTION_MODULE.md
        for why this module doesn't reuse analytics.ElectionResultSnapshot).
        """
        results = []
        for position in self.positions.all().order_by("display_order", "title"):
            candidates = list(
                self.candidates.filter(position=position)
                .annotate(vote_count=models.Count("votes"))
                .order_by("-vote_count", "name")
            )
            total = sum(c.vote_count for c in candidates)
            rows = [
                {
                    "candidate": c,
                    "vote_count": c.vote_count,
                    "percentage": round(c.vote_count / total * 100, 1) if total else 0.0,
                }
                for c in candidates
            ]
            results.append({"position": position, "candidates": rows, "total_votes": total})
        return results


class Candidate(models.Model):
    election = models.ForeignKey(Election, on_delete=models.CASCADE, related_name="candidates")
    position = models.ForeignKey(Position, on_delete=models.PROTECT, related_name="candidates")
    name = models.CharField(max_length=255)
    photo = models.ImageField(upload_to="elections/candidates/%Y/%m/", blank=True, null=True)
    manifesto = models.TextField(blank=True)

    class Meta:
        ordering = ["position__display_order", "name"]
        constraints = [
            # "Candidate cannot appear twice for same position in same
            # election" — this is about blocking an accidental *duplicate
            # entry* (the same name added twice for President in this
            # election), not about limiting how many different candidates
            # can contest one position, which is the entire point of an
            # election. Re-using a name for the same position in a
            # *different* election (someone running again next year) is
            # still allowed.
            models.UniqueConstraint(
                fields=["election", "position", "name"], name="unique_candidate_name_per_position_per_election"
            )
        ]
        verbose_name = "Candidate"
        verbose_name_plural = "Candidates"

    def __str__(self):
        return f"{self.name} — {self.position}"

    def clean(self):
        if self.position_id and self.election_id:
            if self.position.association_id != self.election.association_id:
                raise ValidationError(
                    {"position": "Position must belong to the same association as the election."}
                )
            # self.pk check: an unsaved Candidate can't query its own M2M
            # membership via self.election.positions (the election side is
            # fine either way; this guards the case where election itself
            # is also unsaved, e.g. validating a bound but unsaved form).
            if self.election_id and not self.election.positions.filter(pk=self.position_id).exists():
                raise ValidationError(
                    {"position": "This position is not contested in the selected election. Add it to the election's positions first."}
                )


class Vote(models.Model):
    election = models.ForeignKey(Election, on_delete=models.PROTECT, related_name="votes")
    member = models.ForeignKey(
        "members.Member", on_delete=models.PROTECT, related_name="votes"
    )
    candidate = models.ForeignKey(Candidate, on_delete=models.PROTECT, related_name="votes")
    # Denormalized from candidate.position, deliberately. A DB-level
    # UniqueConstraint can only reference columns that actually live on
    # this table — it can't reach through candidate.position — so the
    # position is copied onto Vote itself (auto-assigned in clean()/save(),
    # never set by hand) purely so "one vote per member per position" can
    # be a real database constraint instead of an application-level check
    # that a bug or a race could slip past.
    position = models.ForeignKey(
        Position, on_delete=models.PROTECT, related_name="votes", editable=False
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        constraints = [
            # The core integrity guarantee: an approved member can cast at
            # most one vote per position within a given election. Two
            # concurrent requests racing to vote for the same member/
            # election/position can't both succeed — the second INSERT
            # fails this constraint rather than racing past an
            # application-level check.
            models.UniqueConstraint(
                fields=["election", "member", "position"], name="unique_vote_per_member_per_position"
            )
        ]
        verbose_name = "Vote"
        verbose_name_plural = "Votes"

    def __str__(self):
        return f"{self.member} -> {self.candidate} ({self.position})"

    def _assign_position(self):
        """Keep `position` in lockstep with `candidate.position` — never set independently."""
        if self.candidate_id:
            self.position_id = self.candidate.position_id

    def clean(self):
        self._assign_position()
        if self.candidate_id and self.election_id and self.candidate.election_id != self.election_id:
            raise ValidationError({"candidate": "Candidate does not belong to the selected election."})
        if self.member_id and not self.member.voting_status:
            raise ValidationError({"member": "This member is not currently eligible to vote."})
        if self.election_id and not self.election.is_voting_open:
            raise ValidationError({"election": "Voting is not currently open for this election."})
        # Election Eligibility Engine (v2.0): re-checked here, at the
        # model layer, on top of the view-level check in
        # elections/views.py — this is the check that still holds even
        # if a vote is ever created through some path other than the
        # ballot view (an admin action, a future API, a script), so
        # eligibility can never be bypassed by skipping the view.
        if self.member_id and self.election_id and not self.election.is_member_eligible(self.member):
            raise ValidationError({"member": "This member is not eligible to vote in this election."})

    def save(self, *args, **kwargs):
        self._assign_position()
        super().save(*args, **kwargs)

