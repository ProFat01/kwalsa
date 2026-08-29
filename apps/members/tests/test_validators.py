from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from apps.members.validators import nin_validator, phone_number_validator


class PhoneNumberValidatorTests(SimpleTestCase):
    def test_valid_phone_numbers_accepted(self):
        for valid in ["08012345678", "07012345678", "09112345678", "08112345678"]:
            phone_number_validator(valid)  # should not raise

    def test_rejects_non_digits(self):
        with self.assertRaises(ValidationError) as ctx:
            phone_number_validator("080abc45678")
        self.assertEqual(ctx.exception.code, "invalid_phone_digits")

    def test_rejects_wrong_length(self):
        with self.assertRaises(ValidationError) as ctx:
            phone_number_validator("0801234567")  # 10 digits
        self.assertEqual(ctx.exception.code, "invalid_phone_length")

    def test_rejects_invalid_prefix(self):
        with self.assertRaises(ValidationError) as ctx:
            phone_number_validator("06012345678")  # valid length/digits, bad prefix
        self.assertEqual(ctx.exception.code, "invalid_phone_prefix")


class NinValidatorTests(SimpleTestCase):
    def test_valid_nin_accepted(self):
        nin_validator("12345678901")  # should not raise

    def test_rejects_non_digits(self):
        with self.assertRaises(ValidationError) as ctx:
            nin_validator("1234abcd901")
        self.assertEqual(ctx.exception.code, "invalid_nin_digits")

    def test_rejects_wrong_length(self):
        with self.assertRaises(ValidationError) as ctx:
            nin_validator("123456789")  # 9 digits
        self.assertEqual(ctx.exception.code, "invalid_nin_length")
