"""Regression tests for the transparent future-budget suggestion engine."""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from core.future_budget_services import build_future_budget_lines, get_future_budget_summary
from core.models import (
    Account, AccountHead, Budget, BudgetLine, BudgetType, FinancialYear,
    FutureBudget, FutureBudgetKnownChange, FutureBudgetPersonnel, Transaction,
)


class FutureBudgetEngineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        account = Account.objects.create(code='FBE', name='Future Budget Engine Test')
        source = FinancialYear.objects.create(
            code='FBE-25', name='FY FBE 2025-26', start_date=date(2025, 7, 1),
            end_date=date(2026, 6, 30), status=FinancialYear.Status.CLOSED,
        )
        target = FinancialYear.objects.create(
            code='FBE-26', name='FY FBE 2026-27', start_date=date(2026, 7, 1),
            end_date=date(2027, 6, 30), status=FinancialYear.Status.OPEN,
        )
        routine = AccountHead.objects.create(account=account, code='FBE-R', name='Routine Requirement')
        salary = AccountHead.objects.create(account=account, code='FBE-S', name='Contract Salaries')
        bt = BudgetType.objects.create(code='FBE-B', name='FBE Budget Type')
        budget = Budget.objects.create(account=account, financial_year=source, status=Budget.Status.APPROVED)
        BudgetLine.objects.create(budget=budget, account_head=routine, budget_type=bt, amount=Decimal('90000.00'))
        BudgetLine.objects.create(budget=budget, account_head=salary, budget_type=bt, amount=Decimal('100000.00'))

        for month in range(7, 15):
            year = 2025 if month <= 12 else 2026
            real_month = month if month <= 12 else month - 12
            Transaction.objects.create(
                account=account, financial_year=source, account_head=routine,
                transaction_date=date(year, real_month, 15), direction=Transaction.Direction.OUTFLOW,
                amount=Decimal('10000.00'), status=Transaction.Status.ACTIVE, is_historical=True,
            )
        Transaction.objects.create(
            account=account, financial_year=source, account_head=salary,
            transaction_date=date(2026, 3, 15), direction=Transaction.Direction.OUTFLOW,
            amount=Decimal('100000.00'), status=Transaction.Status.ACTIVE, is_historical=True,
        )

        future = FutureBudget.objects.create(
            account=account, source_fy=source, target_fy=target,
            routine_adjustment_pct=Decimal('10.00'),
        )
        FutureBudgetKnownChange.objects.create(
            future_budget=future, account_head=routine, description='New requirement',
            change_type=FutureBudgetKnownChange.ChangeType.NEW,
            amount=Decimal('5000.00'),
        )
        FutureBudgetKnownChange.objects.create(
            future_budget=future, account_head=routine, description='Discontinued item',
            change_type=FutureBudgetKnownChange.ChangeType.DISCONTINUED,
            amount=Decimal('2000.00'),
        )
        FutureBudgetPersonnel.objects.create(
            future_budget=future, category_label='Salary revision',
            current_annual_cost=Decimal('100000.00'), revision_pct=Decimal('10.00'),
        )
        cls.future = future

    def test_known_changes_and_personnel_are_visible_in_suggestion(self):
        build_future_budget_lines(self.future)
        lines = {line.account_head.name: line for line in self.future.lines.all()}
        routine = lines['Routine Requirement']
        salary = lines['Contract Salaries']
        self.assertEqual(routine.known_change_amount, Decimal('3000.00'))
        self.assertEqual(salary.personnel_amount, Decimal('10000.00'))
        self.assertEqual(routine.system_suggested, Decimal('91000.00'))
        self.assertEqual(salary.system_suggested, Decimal('110000.00'))

    def test_summary_exposes_all_planning_components(self):
        build_future_budget_lines(self.future)
        summary = get_future_budget_summary(self.future)
        self.assertEqual(summary['previous_actual_total'], Decimal('180000.00'))
        self.assertEqual(summary['routine_total'], Decimal('80000.00'))
        self.assertEqual(summary['known_changes_total'], Decimal('3000.00'))
        self.assertEqual(summary['personnel_effect_total'], Decimal('10000.00'))
        self.assertEqual(summary['system_suggested_total'], Decimal('201000.00'))
