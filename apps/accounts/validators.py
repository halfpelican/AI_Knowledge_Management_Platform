"""Password complexity for FR-01 (Server-End, Validation rules).

The proposal states the rule exactly: "Password must meet complexity rules (min 8
chars, 1 uppercase, 1 number, 1 special character)." Django's four default
validators check none of the last three — a lower-case passphrase of eight letters
satisfies all of them — so those three conditions were unenforced until this
validator existed.

``ComplexityValidator`` checks all four conditions and reports every one that
failed in a single response, so the registration form can mark each rule rather
than making the user resubmit to discover the next problem. The numbers live in
apps.core.constants; nothing here restates a value.

``MinimumLengthValidator`` is configured from the same constant in
config/settings.py. Both check the length on purpose: the default validator is what
the rest of Django's tooling (``createsuperuser``, a future password-change view)
reaches for, and reading the same constant means they cannot disagree.
"""

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from apps.core.constants import (
    PASSWORD_MINIMUM_DIGITS,
    PASSWORD_MINIMUM_LENGTH,
    PASSWORD_MINIMUM_SPECIAL,
    PASSWORD_MINIMUM_UPPERCASE,
    PASSWORD_SPECIAL_CHARACTERS,
)


class ComplexityValidator:
    """FR-01's four complexity rules, in one AUTH_PASSWORD_VALIDATORS entry."""

    def __init__(
        self,
        minimum_length: int = PASSWORD_MINIMUM_LENGTH,
        minimum_uppercase: int = PASSWORD_MINIMUM_UPPERCASE,
        minimum_digits: int = PASSWORD_MINIMUM_DIGITS,
        minimum_special: int = PASSWORD_MINIMUM_SPECIAL,
        special_characters=PASSWORD_SPECIAL_CHARACTERS,
    ):
        self.minimum_length = minimum_length
        self.minimum_uppercase = minimum_uppercase
        self.minimum_digits = minimum_digits
        self.minimum_special = minimum_special
        self.special_characters = frozenset(special_characters)

    # --- The four conditions ----------------------------------------------------

    def _counts(self, password: str) -> dict[str, int]:
        return {
            "uppercase": sum(1 for character in password if character.isupper()),
            "digits": sum(1 for character in password if character.isdigit()),
            "special": sum(1 for character in password if character in self.special_characters),
        }

    def validate(self, password, user=None):
        errors = []
        if len(password) < self.minimum_length:
            errors.append(
                ValidationError(
                    ngettext(
                        "This password is too short. It must contain at least "
                        "%(minimum)d character.",
                        "This password is too short. It must contain at least "
                        "%(minimum)d characters.",
                        self.minimum_length,
                    ),
                    code="password_too_short",
                    params={"minimum": self.minimum_length},
                )
            )
        counts = self._counts(password)
        for kind, required, message, code in (
            (
                "uppercase",
                self.minimum_uppercase,
                ngettext(
                    "This password must contain at least %(minimum)d uppercase letter.",
                    "This password must contain at least %(minimum)d uppercase letters.",
                    self.minimum_uppercase,
                ),
                "password_no_upper",
            ),
            (
                "digits",
                self.minimum_digits,
                ngettext(
                    "This password must contain at least %(minimum)d number.",
                    "This password must contain at least %(minimum)d numbers.",
                    self.minimum_digits,
                ),
                "password_no_digit",
            ),
            (
                "special",
                self.minimum_special,
                ngettext(
                    "This password must contain at least %(minimum)d special character "
                    "(%(characters)s).",
                    "This password must contain at least %(minimum)d special characters "
                    "(%(characters)s).",
                    self.minimum_special,
                ),
                "password_no_special",
            ),
        ):
            if counts[kind] < required:
                errors.append(
                    ValidationError(
                        message,
                        code=code,
                        params={"minimum": required, "characters": self._special_display()},
                    )
                )
        if errors:
            raise ValidationError(errors)

    # --- Help text (the registration form's strength meter, FR-01 Front-End) ------

    def _special_display(self) -> str:
        return "".join(sorted(self.special_characters))

    def get_help_text(self):
        return _(
            "Your password must contain at least %(length)d characters, "
            "%(upper)d uppercase letter, %(digit)d number and %(special)d special "
            "character (%(characters)s)."
        ) % {
            "length": self.minimum_length,
            "upper": self.minimum_uppercase,
            "digit": self.minimum_digits,
            "special": self.minimum_special,
            "characters": self._special_display(),
        }
