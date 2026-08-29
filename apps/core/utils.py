from django.db import IntegrityError, transaction

from .models import SequenceCounter


@transaction.atomic
def get_next_sequence(association, key: str) -> int:
    """
    Atomically increment and return the next integer in a named sequence,
    scoped to one association. Safe under concurrent calls because the
    counter row is locked (`select_for_update`) for the duration of the
    transaction, so two requests racing to register at the same instant
    are serialised at the database level rather than both reading the
    same "next" value.

    Note on the very first call for a brand-new (association, key) pair:
    `select_for_update` can't lock a row that doesn't exist yet, so two
    *simultaneous first* calls could both attempt to create the counter
    row and one would hit the unique constraint. We catch that one-time
    IntegrityError and retry, after which the row exists and the normal
    locked path takes over for every subsequent call.

    Usage:
        n = get_next_sequence(association, "membership_id")
        membership_id = f"{association.short_name}-{timezone.now().year}-{n:04d}"
    """
    try:
        counter, _ = SequenceCounter.objects.select_for_update().get_or_create(
            association=association, key=key
        )
    except IntegrityError:
        counter = SequenceCounter.objects.select_for_update().get(
            association=association, key=key
        )
    counter.last_value += 1
    counter.save(update_fields=["last_value"])
    return counter.last_value
