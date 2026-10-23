from decimal import Decimal

import pytest

from core.future_budget_workbook_contract import calculation_detail_row, build_controls
from core.models import Account, AccountHead, FinancialYear, FutureBudget, FutureBudgetLine


@pytest.fixture
def workbook_line(db):
    account = Account.objects.create(name="G23 Workbook Account")
    source = FinancialYear.objects.create(name="2045-46")
    target = FinancialYear.objects.create(name="2046-47")
    head = AccountHead.objects.create(name="G23 Workbook Head", account=account)
    budget = FutureBudget.objects.create(account=account, source_fy=source, target_fy=target)
    return FutureBudgetLine.objects.create(
        future_budget=budget,
        account_head=head,
        previous_budget=Decimal("1000.00"),
        previous_actual=Decimal("900.00"),
        system_suggested=Decimal("990.00"),
        user_proposed=Decimal("1000.00"),
        approved_amount=Decimal("1000.00"),
        suggestion_breakdown={
            "previous_actual": "900.00",
            "routine_adjustment": "45.00",
            "continuing_requirement": "20.00",
            "management_additional_requirement": "15.00",
            "known_changes": "10.00",
            "personnel_effect": "0.00",
            "onetime_deduction": "0.00",
        },
    )


def test_calculation_detail_uses_canonical_breakdown(workbook_line):
    row = calculation_detail_row(workbook_line)
    assert row["Recurring Baseline"] == Decimal("900.00")
    assert row["Routine Adjustment"] == Decimal("45.00")
    assert row["Continuing Requirement"] == Decimal("20.00")
    assert row["Management Additional"] == Decimal("15.00")
    assert row["Known Changes"] == Decimal("10.00")
    assert row["Personnel Effect"] == Decimal("0.00")
    assert row["System Suggested"] == Decimal("990.00")
    assert row["Management Proposed"] == Decimal("1000.00")
    assert row["Approved Amount"] == Decimal("1000.00")


def test_controls_flag_approved_without_proposal(db):
    account = Account.objects.create(name="G23 Control Account")
    source = FinancialYear.objects.create(name="2047-48")
    target = FinancialYear.objects.create(name="2048-49")
    head = AccountHead.objects.create(name="G23 Control Head", account=account)
    budget = FutureBudget.objects.create(account=account, source_fy=source, target_fy=target)
    line = FutureBudgetLine.objects.create(
        future_budget=budget,
        account_head=head,
        system_suggested=Decimal("50.00"),
        approved_amount=Decimal("50.00"),
    )
    controls = build_controls([line])
    assert any("APPROVED WITHOUT PROPOSAL" in r["Status"] for r in controls)
