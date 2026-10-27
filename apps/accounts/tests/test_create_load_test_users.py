"""``manage.py create_load_test_users`` — the load tests' Employees (D-82 rule 6).

The k6 scripts sign in one account per virtual user, ``loadtest01@example.com`` onwards, with the
password in ``LOAD_TEST_PASSWORD``. These tests hold the command to that interface: the
addresses, the names and the role; the password taken from the environment, checked against
FR-01's rules and never printed; a second run that converges rather than fails; and the refusals
that keep it off a deployed database.
"""

from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.core.constants import EMPLOYEE_ROLE_NAME, LOCKOUT_DURATION, LOCKOUT_THRESHOLD
from conftest import PASSWORD

pytestmark = pytest.mark.django_db

User = get_user_model()

# Satisfies FR-01's rules and resembles neither an address nor a name below.
LOAD_TEST_PASSWORD = "Quarry-Lantern-47!"
LOCAL = "--i-know-this-is-local"


@pytest.fixture
def load_test_password(monkeypatch):
    monkeypatch.setenv("LOAD_TEST_PASSWORD", LOAD_TEST_PASSWORD)
    return LOAD_TEST_PASSWORD


def run(*args):
    """The command's stdout and stderr, joined, so a test can look for the password in both."""
    out, err = StringIO(), StringIO()
    call_command("create_load_test_users", *args, stdout=out, stderr=err)
    return out.getvalue() + err.getvalue()


def load_test_users():
    return User.objects.filter(email__startswith="loadtest").select_related("role").order_by("email")


# --- What it creates ---------------------------------------------------------------------------


def test_it_creates_numbered_employees_who_sign_in_with_the_environments_password(
    load_test_password, api_client
):
    output = run("--count", "12", LOCAL)

    users = list(load_test_users())
    assert [user.email for user in users] == [f"loadtest{n:02d}@example.com" for n in range(1, 13)]
    assert [user.name for user in users] == [f"Load Test {n:02d}" for n in range(1, 13)]
    assert {user.role.role_name for user in users} == {EMPLOYEE_ROLE_NAME}
    assert all(user.check_password(load_test_password) for user in users)
    assert load_test_password not in output
    # The way the k6 scripts will use one: FR-02's login, answered 200.
    response = api_client.post(
        "/api/auth/login",
        {"email": "loadtest07@example.com", "password": load_test_password},
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["role"] == EMPLOYEE_ROLE_NAME


def test_it_runs_without_the_flag_when_debug_is_on(load_test_password, settings):
    settings.DEBUG = True

    run("--count", "2")

    assert load_test_users().count() == 2


# --- Run again: it converges ------------------------------------------------------------------


def test_a_second_run_creates_nothing_new_and_resets_each_password_to_the_environments(
    load_test_password, monkeypatch
):
    """Idempotent: the rows are kept and the password follows the environment. A lock or a
    failed-attempt count an earlier run left behind is cleared, or that account's logins would
    fail the load test."""
    run("--count", "3", LOCAL)
    first_ids = list(load_test_users().values_list("pk", flat=True))
    User.objects.filter(email="loadtest02@example.com").update(
        failed_attempts=LOCKOUT_THRESHOLD, locked_until=timezone.now() + LOCKOUT_DURATION
    )
    monkeypatch.setenv("LOAD_TEST_PASSWORD", "Another-Lantern-58!")

    output = run("--count", "3", LOCAL)

    users = list(load_test_users())
    assert [user.pk for user in users] == first_ids
    assert all(user.check_password("Another-Lantern-58!") for user in users)
    assert not any(user.check_password(LOAD_TEST_PASSWORD) for user in users)
    assert all(user.failed_attempts == 0 and user.locked_until is None for user in users)
    assert "Another-Lantern-58!" not in output
    assert "0 created and 3 reset" in output


def test_a_larger_count_adds_only_the_missing_accounts(load_test_password):
    run("--count", "2", LOCAL)

    output = run("--count", "4", LOCAL)

    assert load_test_users().count() == 4
    assert "2 created and 2 reset" in output


# --- Refusals: nothing is written --------------------------------------------------------------


def test_it_refuses_without_load_test_password(monkeypatch):
    monkeypatch.delenv("LOAD_TEST_PASSWORD", raising=False)

    with pytest.raises(CommandError, match="LOAD_TEST_PASSWORD"):
        run("--count", "3", LOCAL)

    assert not load_test_users().exists()


def test_it_refuses_an_empty_load_test_password(monkeypatch):
    monkeypatch.setenv("LOAD_TEST_PASSWORD", "")

    with pytest.raises(CommandError, match="LOAD_TEST_PASSWORD"):
        run("--count", "3", LOCAL)

    assert not load_test_users().exists()


@pytest.mark.parametrize(
    "weak",
    # The last passes the four complexity rules and fails only the similarity check against the
    # account's name, "Load Test 01", which is why each account is checked as itself.
    ["short1!", "alllowercase-but-long-1", "NoDigitsHere!", "Load-Test-01"],
    ids=["too-short", "no-uppercase", "no-digit", "like-the-name"],
)
def test_it_refuses_a_password_that_fails_fr_01s_rules_and_never_echoes_it(monkeypatch, weak):
    monkeypatch.setenv("LOAD_TEST_PASSWORD", weak)

    with pytest.raises(CommandError, match="fails the password rules") as refused:
        run("--count", "3", LOCAL)

    assert weak not in str(refused.value)
    assert not load_test_users().exists()


def test_it_refuses_to_run_with_debug_off_unless_told_the_database_is_local(
    load_test_password, settings
):
    settings.DEBUG = False

    with pytest.raises(CommandError, match="--i-know-this-is-local"):
        run("--count", "3")

    assert not load_test_users().exists()


def test_it_refuses_an_existing_account_that_is_not_an_employee(load_test_password, monkeypatch):
    """Changing a role is FR-05's, with its audit entry, so the command does not do it; and it
    refuses before writing anything, so the accounts either side are untouched too: the first
    keeps the earlier run's password and the third is not created."""
    run("--count", "1", LOCAL)
    User.objects.create_superuser("loadtest02@example.com", PASSWORD, name="Load Test 02")
    monkeypatch.setenv("LOAD_TEST_PASSWORD", "Another-Lantern-58!")

    with pytest.raises(CommandError, match="loadtest02@example.com exists with the Administrator"):
        run("--count", "3", LOCAL)

    assert [user.email for user in load_test_users()] == [
        "loadtest01@example.com", "loadtest02@example.com"
    ]
    assert User.objects.get(email="loadtest01@example.com").check_password(load_test_password)
    administrator = User.objects.get(email="loadtest02@example.com")
    assert administrator.role.role_name != EMPLOYEE_ROLE_NAME
    assert administrator.check_password(PASSWORD)


@pytest.mark.parametrize("count", ["0", "100"])
def test_the_count_is_one_to_ninety_nine(load_test_password, count):
    with pytest.raises(CommandError, match="between 1 and 99"):
        run("--count", count, LOCAL)

    assert not load_test_users().exists()
