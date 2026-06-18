from django.apps import AppConfig


class RegistryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "registry"
    verbose_name = "NMALIS Registry"

    def ready(self):
        from . import checks  # noqa: F401
