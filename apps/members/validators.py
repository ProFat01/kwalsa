"""
Field-level validators for the members app.

Kept separate from models.py so they're trivially unit-testable and
reusable from future DRF serializers / plain forms without importing the
whole models module.
"""
from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible

# Valid Nigerian mobile network prefixes accepted at registration.
VALID_PHONE_PREFIXES = ("070", "071", "080", "081", "090", "091")


def phone_number_validator(value):
    """
    Phone number must be: digits only, exactly 11 of them, starting with
    one of VALID_PHONE_PREFIXES. Checked in that order and raises on the
    *first* failing rule rather than piling up multiple error messages —
    one clear reason at a time is easier for a registrant to act on than
    three simultaneous complaints about the same field.

    Kept as a plain function (not a RegexValidator instance) specifically
    so each failure mode gets its own precise message; the function is
    still importable at this same dotted path
    (apps.members.validators.phone_number_validator), so the existing
    migration that already references this validator continues to
    resolve correctly — only the implementation changed, not where it
    lives.
    """
    if not value.isdigit():
        raise ValidationError("Phone number must contain numbers only.", code="invalid_phone_digits")
    if len(value) != 11:
        raise ValidationError("Phone number must be exactly 11 digits.", code="invalid_phone_length")
    if value[:3] not in VALID_PHONE_PREFIXES:
        raise ValidationError(
            "Phone number must start with one of: " + ", ".join(VALID_PHONE_PREFIXES) + ".",
            code="invalid_phone_prefix",
        )


def nin_validator(value):
    """NIN must be digits only, exactly 11 of them. Same one-reason-at-a-time approach as phone_number_validator."""
    if not value.isdigit():
        raise ValidationError("NIN must contain numbers only.", code="invalid_nin_digits")
    if len(value) != 11:
        raise ValidationError("NIN must be exactly 11 digits.", code="invalid_nin_length")


@deconstructible
class MaxFileSizeValidator:
    """
    Rejects uploads above `max_mb` megabytes. Used on passport_photo,
    receipt_image, and candidate photo so a single oversized upload can't
    quietly fill the server's disk (a real risk on PythonAnywhere's
    capped storage).
    """

    def __init__(self, max_mb=5):
        self.max_mb = max_mb

    def __call__(self, file):
        max_bytes = self.max_mb * 1024 * 1024
        if file.size > max_bytes:
            raise ValidationError(
                f"File too large ({file.size / (1024 * 1024):.1f} MB). "
                f"Maximum allowed size is {self.max_mb} MB.",
                code="file_too_large",
            )

    def __eq__(self, other):
        return isinstance(other, MaxFileSizeValidator) and self.max_mb == other.max_mb


validate_image_size = MaxFileSizeValidator(max_mb=5)
