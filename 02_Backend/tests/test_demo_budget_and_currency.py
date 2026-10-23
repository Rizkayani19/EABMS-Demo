from django.conf import settings
from django.core.management import call_command
from django.test import TestCase

from core.budget_inflow_models import BudgetInflowLine
from core.models import Account, Budget, BudgetLine, FinancialYear
from core.templatetags import abms_filters


class DemoBudgetSeedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_eabms_corporate', verbosity=0)
        call_command('seed_eabms_demo_transactions', verbosity=0)

    def test_creates_approved_budget_with_outflow_and_inflow_lines(self):
        call_command('seed_eabms_demo_budget', verbosity=0)
        budget = Budget.objects.get(account__code='NGL', financial_year__code='2026-27')
        self.assertEqual(budget.status, Budget.Status.APPROVED)
        self.assertGreater(budget.lines.count(), 0)
        self.assertGreater(budget.inflow_lines.count(), 0)
        self.assertTrue(all(line.amount % 1000 == 0 and line.amount > 0 for line in budget.lines.all()))

    def test_rerun_replaces_lines_instead_of_duplicating(self):
        call_command('seed_eabms_demo_budget', verbosity=0)
        first = (BudgetLine.objects.count(), BudgetInflowLine.objects.count())
        call_command('seed_eabms_demo_budget', verbosity=0)
        self.assertEqual((BudgetLine.objects.count(), BudgetInflowLine.objects.count()), first)
        self.assertEqual(Budget.objects.filter(account__code='NGL').count(), 1)

    def test_does_not_overwrite_a_real_budget(self):
        account = Account.objects.get(code='NGL')
        fy = FinancialYear.objects.get(code='2026-27')
        Budget.objects.create(account=account, financial_year=fy, reference='BRD/2026/014')
        call_command('seed_eabms_demo_budget', verbosity=0)
        budget = Budget.objects.get(account=account, financial_year=fy)
        self.assertEqual(budget.reference, 'BRD/2026/014')
        self.assertEqual(budget.lines.count(), 0)


class CurrencyAndDatabaseDefaultsTests(TestCase):
    def test_currency_defaults_to_rupees(self):
        self.assertEqual(settings.ABMS_CURRENCY_SYMBOL, 'Rs')
        self.assertEqual(abms_filters.CURRENCY_SYMBOL, 'Rs')

    def test_development_without_database_settings_uses_sqlite(self):
        if settings.IS_PRODUCTION:
            self.skipTest('Only applies to development settings')
        engine = settings.DATABASES['default']['ENGINE']
        if settings.DB_ENGINE in ('postgresql', 'postgres', 'psycopg2'):
            self.assertEqual(engine, 'django.db.backends.postgresql')
        else:
            self.assertEqual(engine, 'django.db.backends.sqlite3')
