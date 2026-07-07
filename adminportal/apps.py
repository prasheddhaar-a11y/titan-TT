from django.apps import AppConfig


class AdminportalConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'adminportal'

    def ready(self):
        # Registers the user_logged_in / user_logged_out handlers that
        # enforce single-session-per-account behavior. Must be imported
        # here (not at module top-level) so Django's app registry is
        # fully ready before adminportal.signals imports adminportal.models.
        import adminportal.signals  # noqa: F401