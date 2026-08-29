from django.apps import AppConfig


class MembersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.members"
    verbose_name = "Members"

    def ready(self):
        from . import signals  # noqa: F401  (registers @receiver hooks)
