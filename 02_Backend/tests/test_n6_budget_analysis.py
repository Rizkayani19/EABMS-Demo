"""N6 — Existing budget analysis and future-budget baseline tests."""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from core.budget_analysis_services import (
    analyse_budget,
    monthly_actuals,
    variance_flags,
    build_future_baseline,
)
from core.models import (
    Account,
    AccountHead,
    Budget,
    BudgetLine,
    BudgetType,
    FinancialYear,
    Transaction,
)


class N6BudgetAnalysisTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        account = Account.objects.create(code="N6", name="N6 Test Account")
        fy = FinancialYear.objects.create(
            code="N6-25-26", name="FY N6 2025-26",
            start_date=date(2025, 7, 1), end_date=date(2026, 6, 30),
            status=FinancialYear.Status.CLOSED,
        )
        target = FinancialYear.objects.create(
            code="N6-26-27", name="FY N6 2026-27",
            start_date=date(2026, 7, 1), end_date=date(2027, 6, 30),
            status=FinancialYear.Status.OPEN,
        )
        head_a = AccountHead.objects.create(account=account, code="N6-A", name="Routine A")
        head_b = AccountHead.objects.create(account=account, code="N6-B", name="One Time B")
        bt = BudgetType.objects.create(code="N6-APP", name="N6 Approved")
        budget = Budget.objects.create(account=account, financial_year=fy, status=Budget.Status.APPROVED)
        BudgetLine.objects.create(budget=budget, account_head=head_a, budget_type=bt, amount=Decimal("100000.00"))
        BudgetLine.objects.create(budget=budget, account_head=head_b, budget_type=bt, amount=Decimal("50000.00"))

        # A: recurring across 8 months; B: one-time in one month.
        for month in range(7, 15):
            year = 2025 if month <= 12 else 2026
            real_month = month if month <= 12 else month - 12
            Transaction.objects.create(
                account=account, financial_year=fy, account_head=head_a,
                transaction_date=date(year, real_month, 15),
                direction=Transaction.Direction.OUTFLOW,
                amount=Decimal("10000.00"), status=Transaction.Status.ACTIVE,
                is_historical=True,
            )
        Transaction.objects.create(
            account=account, financial_year=fy, account_head=head_b,
            transaction_date=date(2026, 3, 15), direction=Transaction.Direction.OUTFLOW,
            amount=Decimal("25000.00"), status=Transaction.Status.ACTIVE,
            is_historical=True,
        )
        cls.account, cls.source_fy, cls.target_fy = account, fy, target

    def test_budget_actual_reconciles_to_transaction_source(self):
        result = analyse_budget(self.account, self.source_fy)
        self.assertEqual(result["total_budget"], Decimal("150000.00"))
        self.assertEqual(result["total_actual"], Decimal("105000.00"))
        self.assertEqual(result["reconciliation_difference"], Decimal("0.00"))

    def test_monthly_output_has_12_periods(self):
        result = monthly_actuals(self.account, self.source_fy)
        self.assertEqual(len(result), 12)
        self.assertEqual(sum((r["amount"] for r in result), Decimal("0.00")), Decimal("105000.00"))

    def test_material_variance_flags(self):
        result = analyse_budget(self.account, self.source_fy)
        flags = variance_flags(result)
        self.assertTrue(any(f["flag"] == "MATERIAL UNDER-UTILISATION" for f in flags))

    def test_future_baseline_separates_one_time_requirement(self):
        future = build_future_baseline(
            self.account, self.source_fy, self.target_fy, Decimal("10.00")
        )
        lines = {line.account_head.name: line for line in future.lines.all()}
        self.assertEqual(lines["Routine A"].previous_actual, Decimal("80000.00"))
        self.assertEqual(lines["Routine A"].system_suggested, Decimal("88000.00"))
        self.assertEqual(lines["One Time B"].onetime_amount, Decimal("25000.00"))
        self.assertEqual(lines["One Time B"].system_suggested, Decimal("0.00"))
