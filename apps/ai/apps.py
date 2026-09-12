from django.apps import AppConfig


class AiConfig(AppConfig):
    name = "apps.ai"
    label = "ai"

    def ready(self):
        # Importing the module registers the startup check under the ``ai`` tag.
        from apps.ai import checks  # noqa: F401
