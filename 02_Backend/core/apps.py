from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    verbose_name = 'ABMS Core & Isolation Architecture'

    def ready(self):
        from . import signals  # noqa: F401
        from . import future_budget_allocation_models  # noqa: F401
        from . import historical_budget_allocation_models  # noqa: F401
        from . import future_budget_management_models  # noqa: F401
        from . import budget_inflow_models  # noqa: F401
