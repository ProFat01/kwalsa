from django.utils import timezone

from apps.core.utils import get_next_sequence


def generate_membership_id(association) -> str:
    """
    Format: <SHORT_NAME>-<YEAR>-<0001>
    e.g. MSA-2026-0001

    Only called once a RegistrationApplication is approved (see
    members/signals.py) — unapproved members never get a membership_id,
    which is itself a cheap extra guard against an unapproved record
    being mistaken for a real member anywhere downstream.
    """
    year = timezone.now().year
    n = get_next_sequence(association, "membership_id")
    return f"{association.short_name}-{year}-{n:04d}"


def generate_application_number(association) -> str:
    """
    Format: APP-<YEAR>-<00001>
    e.g. APP-2026-00001

    Note: this intentionally drops the association short_name that the
    very first version of this helper included (APP-MSA-2026-00001) —
    the registration module's spec calls for the shorter
    APP-YYYY-00001 form explicitly. The counter itself is still scoped
    per-association internally (get_next_sequence(association, ...)), so
    today, with a single association, this is exactly equivalent and the
    change is purely cosmetic. The real-world consequence to flag: if a
    second association is ever onboarded, both associations' counters
    independently restart, so two different associations could each mint
    "APP-2026-00001" in the same year — and `application_number` is
    globally unique, so the second one to save would fail outright. If
    multi-tenancy actually launches, reintroducing the association code
    into this string (or moving to a single global counter) is the fix —
    flagged here rather than silently risking it.
    """
    year = timezone.now().year
    n = get_next_sequence(association, "application_number")
    return f"APP-{year}-{n:05d}"
