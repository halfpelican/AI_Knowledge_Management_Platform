"""FR-01 password complexity: apps.accounts.validators.ComplexityValidator (D-25).

The FR states the rule as "min 8 chars, 1 uppercase, 1 number, 1 special character".
These tests exercise the validator directly, so each of the four conditions is
pinned on its own rather than only through the registration endpoint, and they pin
what counts as a special character: ASCII punctuation, whitespace excluded.

The validator needs no database; only the tests that go through
``validate_password`` with a user do.
"""

import string

import pytest
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from apps.accounts.validators import ComplexityValidator
from apps.core.constants import PASSWORD_MINIMUM_LENGTH, PASSWORD_SPECIAL_CHARACTERS

validator = ComplexityValidator()


def codes_for(password: str) -> set[str]:
    """The failure codes ComplexityValidator raises for ``password``, or an empty
    set when it accepts it."""
    try:
        validator.validate(password)
    except ValidationError as error:
        return {inner.code for inner in error.error_list}
    return set()


# --- Happy path --------------------------------------------------------------------


@pytest.mark.parametrize(
    "password",
    [
        "Correct-Horse-9-Battery",
        "Abcdefg1!",
        "P@ssw0rdish-thing",
        "8Characters!X",
        "A1!" + "z" * 5,  # exactly the minimum length
    ],
)
def test_a_complying_password_is_accepted(password):
    assert codes_for(password) == set()


def test_the_shortest_complying_password_is_exactly_the_minimum():
    password = "Aa1!" + "b" * (PASSWORD_MINIMUM_LENGTH - 4)
    assert len(password) == PASSWORD_MINIMUM_LENGTH
    assert codes_for(password) == set()
    assert codes_for(password[:-1]) == {"password_too_short"}


# --- Each rule, alone --------------------------------------------------------------


@pytest.mark.parametrize(
    ("password", "code"),
    [
        ("Ab1!efg", "password_too_short"),  # 7 characters, everything else present
        ("abcdefg1!", "password_no_upper"),
        ("Abcdefgh!", "password_no_digit"),
        ("Abcdefg1", "password_no_special"),
    ],
)
def test_each_rule_is_enforced_on_its_own(password, code):
    assert codes_for(password) == {code}


def test_every_unmet_rule_is_reported_at_once():
    """The registration form marks each failing rule, so one submission has to
    report them all rather than revealing the next only after a resubmission."""
    assert codes_for("abc") == {
        "password_too_short",
        "password_no_upper",
        "password_no_digit",
        "password_no_special",
    }


# --- What counts as a special character (the server's definition is authoritative) ---


@pytest.mark.parametrize("character", sorted(string.punctuation))
def test_every_ascii_punctuation_character_is_special(character):
    assert codes_for(f"Abcdefg1{character}") == set()


@pytest.mark.parametrize("character", [" ", "\t", "\n"])
def test_whitespace_is_not_a_special_character(character):
    # A passphrase must not satisfy the rule with a space.
    assert codes_for(f"Abcdefg1{character}") == {"password_no_special"}


def test_a_letter_or_a_digit_is_not_a_special_character():
    assert codes_for("Abcdefg1z") == {"password_no_special"}
    assert codes_for("Abcdefg12") == {"password_no_special"}


def test_the_special_set_is_the_constant():
    assert validator.special_characters == PASSWORD_SPECIAL_CHARACTERS


# --- Help text (FR-01's front-end strength meter shows the same rules) --------------


def test_help_text_names_all_four_rules():
    help_text = ComplexityValidator().get_help_text()
    assert str(PASSWORD_MINIMUM_LENGTH) in help_text
    for word in ("uppercase", "number", "special"):
        assert word in help_text


# --- Wired into validate_password, next to Django's own validators ------------------


@pytest.mark.django_db
def test_validate_password_applies_the_complexity_rules(employee):
    with pytest.raises(ValidationError) as raised:
        validate_password("lowercase-only", user=employee)
    codes = {error.code for error in raised.value.error_list}
    assert {"password_no_upper", "password_no_digit"} <= codes


@pytest.mark.django_db
def test_validate_password_accepts_the_suites_password(employee):
    from conftest import PASSWORD

    validate_password(PASSWORD, user=employee)  # raises nothing
