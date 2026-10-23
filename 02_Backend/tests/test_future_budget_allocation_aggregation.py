from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from core.future_budget_allocation import FutureBudgetAllocationService
from core.models import (
    Account,
    AccountHead,
    FinancialYear,
    FutureBudget,
    FutureBudgetLine,
    Unit,
    InternalSection,
)


@pytest.fixture
def aggregation_context(db):
    account = Account.objects.create(name="G24 Aggregation Account")

    fy = FinancialYear.objects.create(
        code="2041-42",
        name="2041-42",
        start_date=date(2041, 7, 1),
        end_date=date(2042, 6, 30),
    )

    head_1 = AccountHead.objects.create(
        name="G24 Aggregation Head 1",
        account=account,
    )

    head_2 = AccountHead.objects.create(
        name="G24 Aggregation Head 2",
        account=account,
    )

    source_fy = FinancialYear.objects.create(
    code="2040-41",
    name="2040-41",
    start_date=date(2040, 7, 1),
    end_date=date(2041, 6, 30),
    )

    budget = FutureBudget.objects.create(
        account=account,
        target_fy=fy,
        source_fy=source_fy,
    )

    line_1 = FutureBudgetLine.objects.create(
        future_budget=budget,
        account_head=head_1,
        system_suggested=Decimal("1000.00"),
    )

    line_2 = FutureBudgetLine.objects.create(
        future_budget=budget,
        account_head=head_2,
        system_suggested=Decimal("2000.00"),
    )

    unit_a = Unit.objects.create(
        code="G24-A",
        name="G24 Unit A",
    )

    unit_b = Unit.objects.create(
        code="G24-B",
        name="G24 Unit B",
    )

    section_a = InternalSection.objects.create(
        code="G24-SA",
        name="G24 Section A",
    )

    section_b = InternalSection.objects.create(
        code="G24-SB",
        name="G24 Section B",
    )

    user = get_user_model().objects.create_user(
        username="g24_allocator",
    )

    return {
        "budget": budget,
        "line_1": line_1,
        "line_2": line_2,
        "unit_a": unit_a,
        "unit_b": unit_b,
        "section_a": section_a,
        "section_b": section_b,
        "user": user,
    }


def test_single_line_multiple_units_reconcile_exactly(aggregation_context):
    ctx = aggregation_context

    FutureBudgetAllocationService.allocate(
        ctx["line_1"],
        "600.00",
        ctx["user"],
        unit=ctx["unit_a"],
    )

    FutureBudgetAllocationService.allocate(
        ctx["line_1"],
        "400.00",
        ctx["user"],
        unit=ctx["unit_b"],
    )

    result = FutureBudgetAllocationService.reconcile(ctx["line_1"])

    assert result["allocated"] == Decimal("1000.00")
    assert result["difference"] == Decimal("0.00")
    assert result["status"] == "RECONCILED"


def test_single_line_unit_and_section_allocations_are_aggregated(
    aggregation_context,
):
    ctx = aggregation_context

    FutureBudgetAllocationService.allocate(
        ctx["line_1"],
        "250.00",
        ctx["user"],
        unit=ctx["unit_a"],
    )

    FutureBudgetAllocationService.allocate(
        ctx["line_1"],
        "250.00",
        ctx["user"],
        internal_section=ctx["section_a"],
    )

    FutureBudgetAllocationService.allocate(
        ctx["line_1"],
        "500.00",
        ctx["user"],
        unit=ctx["unit_b"],
        internal_section=ctx["section_b"],
    )

    result = FutureBudgetAllocationService.reconcile(ctx["line_1"])

    assert result["allocated"] == Decimal("1000.00")
    assert result["difference"] == Decimal("0.00")
    assert result["status"] == "RECONCILED"


def test_different_budget_lines_remain_independent(aggregation_context):
    ctx = aggregation_context

    FutureBudgetAllocationService.allocate(
        ctx["line_1"],
        "500.00",
        ctx["user"],
        unit=ctx["unit_a"],
    )

    FutureBudgetAllocationService.allocate(
        ctx["line_2"],
        "750.00",
        ctx["user"],
        unit=ctx["unit_b"],
    )

    result_1 = FutureBudgetAllocationService.reconcile(ctx["line_1"])
    result_2 = FutureBudgetAllocationService.reconcile(ctx["line_2"])

    assert result_1["allocated"] == Decimal("500.00")
    assert result_1["difference"] == Decimal("500.00")
    assert result_1["status"] == "UNRECONCILED"

    assert result_2["allocated"] == Decimal("750.00")
    assert result_2["difference"] == Decimal("1250.00")
    assert result_2["status"] == "UNRECONCILED"


def test_parent_line_amounts_are_not_modified_by_multiple_allocations(
    aggregation_context,
):
    ctx = aggregation_context

    original_line_1 = ctx["line_1"].system_suggested
    original_line_2 = ctx["line_2"].system_suggested

    FutureBudgetAllocationService.allocate(
        ctx["line_1"],
        "300.00",
        ctx["user"],
        unit=ctx["unit_a"],
    )

    FutureBudgetAllocationService.allocate(
        ctx["line_1"],
        "200.00",
        ctx["user"],
        unit=ctx["unit_b"],
    )

    FutureBudgetAllocationService.allocate(
        ctx["line_2"],
        "500.00",
        ctx["user"],
        internal_section=ctx["section_a"],
    )

    ctx["line_1"].refresh_from_db()
    ctx["line_2"].refresh_from_db()

    assert ctx["line_1"].system_suggested == original_line_1
    assert ctx["line_2"].system_suggested == original_line_2

    assert ctx["line_1"].user_proposed is None
    assert ctx["line_1"].approved_amount is None

    assert ctx["line_2"].user_proposed is None
    assert ctx["line_2"].approved_amount is None


def test_partial_allocation_reports_exact_remaining_amount(
    aggregation_context,
):
    ctx = aggregation_context

    FutureBudgetAllocationService.allocate(
        ctx["line_1"],
        "375.00",
        ctx["user"],
        unit=ctx["unit_a"],
    )

    result = FutureBudgetAllocationService.reconcile(ctx["line_1"])

    assert result["allocated"] == Decimal("375.00")
    assert result["difference"] == Decimal("625.00")
    assert result["status"] == "UNRECONCILED"


def test_over_allocation_reports_exact_excess_amount(
    aggregation_context,
):
    ctx = aggregation_context

    FutureBudgetAllocationService.allocate(
        ctx["line_1"],
        "1200.00",
        ctx["user"],
        unit=ctx["unit_a"],
    )

    result = FutureBudgetAllocationService.reconcile(ctx["line_1"])

    assert result["allocated"] == Decimal("1200.00")
    assert result["difference"] == Decimal("-200.00")
    assert result["status"] == "UNRECONCILED"


def test_allocation_for_one_line_does_not_affect_another_line(
    aggregation_context,
):
    ctx = aggregation_context

    FutureBudgetAllocationService.allocate(
        ctx["line_1"],
        "1000.00",
        ctx["user"],
        unit=ctx["unit_a"],
    )

    result_1 = FutureBudgetAllocationService.reconcile(ctx["line_1"])
    result_2 = FutureBudgetAllocationService.reconcile(ctx["line_2"])

    assert result_1["status"] == "RECONCILED"
    assert result_1["allocated"] == Decimal("1000.00")

    assert result_2["allocated"] == Decimal("0.00")
    assert result_2["difference"] == Decimal("2000.00")
    assert result_2["status"] == "UNRECONCILED"