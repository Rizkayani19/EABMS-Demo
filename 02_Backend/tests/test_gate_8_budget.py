from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.db.models import Sum

from core.models import (
    Account,
    AccountHead,
    Budget,
    BudgetLine,
    BudgetRevision,
    BudgetType,
    FinancialYear,
    UserProfile,
)
from core.dashboard_services import get_dashboard_data
from reports.services import build_budget_vs_actual


class Gate8BudgetReconciliationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_eabms_corporate", verbosity=0)

        cls.account = Account.objects.get(code="NGL")
        cls.fy = FinancialYear.objects.get(code="2026-27")
        cls.account_heads = list(
            AccountHead.objects.filter(account=cls.account, is_active=True).order_by("id")[:2]
        )
        cls.budget_type = BudgetType.objects.filter(is_active=True).order_by("id").first()

        if len(cls.account_heads) < 2:
            raise AssertionError("Gate 8 budget reconciliation tests require at least two NGL account heads.")
        if cls.budget_type is None:
            raise AssertionError("Gate 8 budget reconciliation tests require an active Budget Type.")

        cls.user = User.objects.create_user(username="gate8_budget", password="pwd")
        UserProfile.objects.create(
            user=cls.user,
            role=UserProfile.Role.ADMINISTRATOR,
            default_account=cls.account,
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def _make_budget(self):
        budget = Budget.objects.create(
            account=self.account,
            financial_year=self.fy,
            status=Budget.Status.APPROVED,
            reference="Gate 8 Budget Test",
        )
        BudgetLine.objects.create(
            budget=budget,
            account_head=self.account_heads[0],
            budget_type=self.budget_type,
            amount=Decimal("1000000.00"),
        )
        BudgetLine.objects.create(
            budget=budget,
            account_head=self.account_heads[1],
            budget_type=self.budget_type,
            amount=Decimal("250000.00"),
        )
        return budget

    def test_1_budget_total_amount_matches_line_sum(self):
        budget = self._make_budget()
        expected = budget.lines.aggregate(total=Sum("amount"))["total"]
        self.assertEqual(budget.total_amount, Decimal(expected).quantize(Decimal("0.01")))
        self.assertEqual(budget.total_amount, Decimal("1250000.00"))


    def test_3_budget_revision_changes_canonical_total(self):
        budget = self._make_budget()
        line = budget.lines.order_by("id").first()
        previous = budget.total_amount

        line.amount = Decimal("1500000.00")
        line.save(update_fields=["amount"])
        BudgetRevision.objects.create(
            budget_line=line,
            previous_amount=Decimal("1000000.00"),
            revised_amount=Decimal("1500000.00"),
            difference=Decimal("500000.00"),
            reason="Gate 8 reconciliation test",
            revised_by=self.user,
        )

        budget.refresh_from_db()
        self.assertEqual(previous, Decimal("1250000.00"))
        self.assertEqual(budget.total_amount, Decimal("1750000.00"))

    def test_4_dashboard_approved_budget_matches_budget_total(self):
        budget = self._make_budget()
        dashboard = get_dashboard_data(self.account, self.fy)
        self.assertEqual(dashboard["approved_budget"], budget.total_amount)

    def test_5_budget_vs_actual_uses_same_approved_line_total(self):
        budget = self._make_budget()
        rows = build_budget_vs_actual({
            "account": self.account,
            "financial_year": self.fy,
        })
        report_total = sum((row["approved_budget"] for row in rows), Decimal("0.00"))
        self.assertEqual(report_total, budget.total_amount)
