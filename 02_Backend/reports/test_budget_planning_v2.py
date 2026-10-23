from decimal import Decimal
from django.test import TestCase
from django.contrib.auth.models import User
from core.models import Account, FinancialYear, AccountHead, Budget, BudgetLine, BudgetType, Transaction, OutflowNature, FutureBudget
from reports.budget_planning_v2 import existing_budget_analysis, budget_driver_analysis, create_future_budget_draft


class BudgetPlanningEngineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='budget_test', password='test')
        cls.account = Account.objects.create(code='TST', name='Test Account')
        cls.source = FinancialYear.objects.create(code='FYTEST1', name='FY Test 1', start_date='2025-07-01', end_date='2026-06-30', status='CLOSED')
        cls.target = FinancialYear.objects.create(code='FYTEST2', name='FY Test 2', start_date='2026-07-01', end_date='2027-06-30', status='OPEN')
        cls.ah = AccountHead.objects.create(account=cls.account, code='TST-01', name='Test Head', head_type='OUTFLOW')
        cls.bt = BudgetType.objects.create(code='TST', name='Test Budget Type')
        cls.nature = OutflowNature.objects.create(code='ROUTINE', name='Routine')
        cls.budget = Budget.objects.create(account=cls.account, financial_year=cls.source, status='APPROVED')
        BudgetLine.objects.create(budget=cls.budget, account_head=cls.ah, budget_type=cls.bt, amount=Decimal('100000.00'))
        Transaction.objects.create(
            transaction_number='TST-TXN-001', account=cls.account, financial_year=cls.source,
            account_head=cls.ah, transaction_date='2025-08-01', direction='OUTFLOW',
            amount=Decimal('90000.00'), outflow_nature=cls.nature, status='ACTIVE',
            is_historical=True,
        )

    def test_existing_budget_variance(self):
        rows = existing_budget_analysis(self.account, self.source)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['budget'], Decimal('100000.00'))
        self.assertEqual(rows[0]['actual'], Decimal('90000.00'))
        self.assertEqual(rows[0]['variance'], Decimal('-10000.00'))

    def test_driver_analysis(self):
        totals = budget_driver_analysis(self.account, self.source)
        self.assertEqual(totals['actual'], Decimal('90000.00'))
        self.assertEqual(totals['routine'], Decimal('90000.00'))

    def test_future_budget_draft(self):
        future = create_future_budget_draft(self.account, self.source, self.target, routine_adjustment_pct=Decimal('10.00'), user=self.user)
        self.assertEqual(future.status, FutureBudget.Status.DRAFT)
        line = future.lines.get(account_head=self.ah)
        self.assertEqual(line.previous_actual, Decimal('90000.00'))
        self.assertEqual(line.system_suggested, Decimal('99000.00'))
