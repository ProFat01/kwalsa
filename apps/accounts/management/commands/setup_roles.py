"""
Creates (or updates) the four staff role Groups and attaches the
permissions declared in apps/accounts/permissions.py.

Run manually after `migrate` (deploy script / first-time setup), and
again any time ROLE_PERMISSIONS changes:

    python manage.py setup_roles

Deliberately a management command rather than a post_migrate signal:
post_migrate fires per-app immediately after that app's own migrations
run, which means a naive signal handler in accounts could fire before
members/elections/analytics have created the Permission rows their
models need (Permission objects are created from each app's own
post_migrate hook, in INSTALLED_APPS order, not all at once). A command
run once after the *whole* `migrate` has finished avoids that ordering
trap entirely, is trivially re-runnable/idempotent, and is explicit in
deploy logs instead of being invisible magic that happens on every
migrate.
"""
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.permissions import ROLE_PERMISSIONS


class Command(BaseCommand):
    help = "Create/update the Super Admin, Registration Admin, Election Admin, and Analytics Admin groups."

    def handle(self, *args, **options):
        for role_name, perm_strings in ROLE_PERMISSIONS.items():
            group, created = Group.objects.get_or_create(name=role_name)
            permissions = []
            missing = []
            for perm_string in perm_strings:
                app_label, codename = perm_string.split(".", 1)
                try:
                    permissions.append(
                        Permission.objects.get(content_type__app_label=app_label, codename=codename)
                    )
                except Permission.DoesNotExist:
                    missing.append(perm_string)

            group.permissions.set(permissions)

            verb = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"{verb} group '{role_name}' with {len(permissions)} permission(s)."))
            if missing:
                self.stdout.write(
                    self.style.WARNING(
                        f"  Skipped {len(missing)} permission(s) not found (run `migrate` first?): {missing}"
                    )
                )

        if not Group.objects.filter(name__in=ROLE_PERMISSIONS.keys()).exists():
            raise CommandError("No groups were created — check ROLE_PERMISSIONS.")
