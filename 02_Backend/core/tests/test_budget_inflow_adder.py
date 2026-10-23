from decimal import Decimal

from django.test import TestCase

from core.budget_inflow_models import BudgetInflowLine
from core.budget_views import BudgetLineAdderForm
from core.models import Account, AccountHead, Budget, BudgetType, FinancialYear


class BudgetInflowAdderTests(TestCase):
    def setUp(self):
        self.account = Account.objects.create(code='TST', name='Test Account')
        self.fy = FinancialYear.objects.create(code='2099-00', name='2099-00', start_date='2099-07-01', end_date='2100-06-30')
        self.budget = Budget.objects.create(account=self.account, financial_year=self.fy, status='DRAFT')
        self.budget_type = BudgetType.objects.create(code='REG', name='Regular', is_active=True)
        self.inflow = AccountHead.objects.create(account=self.account, code='INF', name='Inflow Head', head_type='INFLOW', is_active=True)
        self.both = AccountHead.objects.create(account=self.account, code='BTH', name='Both Head', head_type='BOTH', is_active=True)
        self.outflow = AccountHead.objects.create(account=self.account, code='OUT', name='Outflow Head', head_type='OUTFLOW', is_active=True)

    def test_inflow_head_requires_inflow_amount(self):
        form = BudgetLineAdderForm(
            data={'account_head': self.inflow.pk, 'budget_type': self.budget_type.pk, 'inflow_amount': '', 'amount': ''},
            account=self.account,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('inflow_amount', form.errors)

    def test_both_head_accepts_both_directions(self):
        form = BudgetLineAdderForm(
            data={'account_head': self.both.pk, 'budget_type': self.budget_type.pk, 'inflow_amount': '2500', 'amount': '4000'},
            account=self.account,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_inflow_line_is_separate_from_outflow_budget_line(self):
        line = BudgetInflowLine.objects.create(
            budget=self.budget,
            account_head=self.inflow,
            budget_type=self.budget_type,
            amount=Decimal('2500.00'),
        )
        self.assertEqual(line.amount, Decimal('2500.00'))
        self.assertEqual(self.budget.inflow_lines.count(), 1)
        self.assertEqual(self.budget.inflow_lines.first().account_head, self.inflow)
