from django.test import SimpleTestCase


class CanonicalBaselineSmokeTests(SimpleTestCase):
    def test_core_routing_uses_split_transaction_and_budget_views(self):
        from core import urls

        route_text = '\n'.join(str(pattern.pattern) for pattern in urls.urlpatterns)
        self.assertIn('transactions/', route_text)
        self.assertIn('budgets/', route_text)
        self.assertIn('future-budgets/', route_text)

    def test_reporting_registry_imports(self):
        from reports.registry import registry

        self.assertIsNotNone(registry)
