"""``python manage.py create_load_test_users --count N`` — the load tests' Employees (D-82 rule 6).

The k6 scripts in ``tests/load/`` sign in one account per virtual user, so that no account
passes D-79's per-user limits. This command makes those accounts on a local database:
``loadtest01@example.com`` to ``loadtestNN@example.com``, two digits and zero-padded, named
"Load Test 01" and so on, each an Employee.

**The password is read from the environment variable ``LOAD_TEST_PASSWORD``**, never from an
argument (which would sit in shell history) and never from the repository. It must pass the
same validators registration applies (FR-01), checked against each account before anything is
written. It is never printed.

**Run it again and the accounts converge on the environment.** An address that already exists
keeps its row, its name and its history, has its password reset to ``LOAD_TEST_PASSWORD``, and
has FR-02's failed-attempt counter and lock cleared, so every account signs in with the current
password whatever an earlier run left behind. An existing account whose role is not Employee is
refused before anything is written: changing a role is FR-05's business and writes an audit
entry, and a load test run as an Administrator would measure a different scope.

**Refuses to run unless ``DEBUG`` is on, or ``--i-know-this-is-local`` is given**, so that it
cannot seed known accounts into a deployed database by accident. ``DEBUG`` is off wherever the
platform is deployed (``config/settings.py`` defaults it to off), and a local run that has it
off says so explicitly with the flag.
"""

import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Role
from apps.core.constants import EMPLOYEE_ROLE_NAME

PASSWORD_VARIABLE = "LOAD_TEST_PASSWORD"
# Two digits, zero-padded, so the addresses sort in VU order and the k6 scripts can build them.
MAXIMUM_COUNT = 99
LOCAL_FLAG = "--i-know-this-is-local"


def load_test_email(number: int) -> str:
    return f"loadtest{number:02d}@example.com"


def load_test_name(number: int) -> str:
    return f"Load Test {number:02d}"


class Command(BaseCommand):
    help = (
        "Create or reset the load tests' Employee accounts, loadtest01@example.com onwards, "
        f"with the password in {PASSWORD_VARIABLE}. Local databases only."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            required=True,
            help=f"how many accounts, 1 to {MAXIMUM_COUNT}",
        )
        parser.add_argument(
            LOCAL_FLAG,
            action="store_true",
            dest="i_know_this_is_local",
            help="run even though DEBUG is off; only ever against a local database",
        )

    def handle(self, *args, count, i_know_this_is_local, **options):
        if not settings.DEBUG and not i_know_this_is_local:
            raise CommandError(
                "Refusing to create load-test accounts with DEBUG off, which is how a deployed "
                f"server runs. Against a local database, pass {LOCAL_FLAG}."
            )
        if not 1 <= count <= MAXIMUM_COUNT:
            raise CommandError(f"--count must be between 1 and {MAXIMUM_COUNT}, not {count}.")
        password = os.environ.get(PASSWORD_VARIABLE)
        if not password:
            raise CommandError(
                f"Set {PASSWORD_VARIABLE} in the environment to the password the load-test "
                "accounts should have. It is read from there and never printed."
            )

        User = get_user_model()
        employee_role = Role.objects.get(role_name=EMPLOYEE_ROLE_NAME)
        numbers = range(1, count + 1)
        existing = {
            user.email: user
            for user in User.objects.select_related("role").filter(
                email__in=[load_test_email(number) for number in numbers]
            )
        }

        # Every check first, so a refusal writes nothing.
        planned = []
        for number in numbers:
            email = load_test_email(number)
            account = existing.get(email)
            if account is not None and account.role.role_name != EMPLOYEE_ROLE_NAME:
                raise CommandError(
                    f"{email} exists with the {account.role.role_name} role. The load tests "
                    "run as Employees; change its role through FR-05 or remove the account."
                )
            candidate = account or User(email=email, name=load_test_name(number), role=employee_role)
            try:
                validate_password(password, user=candidate)
            except ValidationError as error:
                # The validators' messages describe the rule broken, never the password.
                raise CommandError(
                    f"{PASSWORD_VARIABLE} fails the password rules for {email}: "
                    + " ".join(error.messages)
                ) from None
            planned.append((number, email, account))

        created = reset = 0
        with transaction.atomic():
            for number, email, account in planned:
                if account is None:
                    User.objects.create_user(
                        email, password, name=load_test_name(number), role=employee_role
                    )
                    created += 1
                    self.stdout.write(f"Created {email}")
                else:
                    account.set_password(password)
                    account.failed_attempts = 0
                    account.locked_until = None
                    account.save(update_fields=["password", "failed_attempts", "locked_until"])
                    reset += 1
                    self.stdout.write(f"Reset the password of {email}")
        self.stdout.write(
            self.style.SUCCESS(
                f"{created} created and {reset} reset: {count} Employee account(s), "
                f"{load_test_email(1)} to {load_test_email(count)}."
            )
        )
