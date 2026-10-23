from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from core.future_budget_allocation import FutureBudgetAllocationService
from core.future_budget_allocation_models import FutureBudgetAllocation
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
def allocation_context(db):
    account = Account.objects.create(
        name="G23 Allocation Account"
    )

    source_fy = FinancialYear.objects.create(
        code="2039-40",
        name="2039-40",
        start_date=date(2039, 7, 1),
        end_date=date(2040, 6, 30),
    )

    target_fy = FinancialYear.objects.create(
        code="2040-41",
        name="2040-41",
        start_date=date(2040, 7, 1),
        end_date=date(2041, 6, 30),
    )

    head = AccountHead.objects.create(
        name="G23 Allocation Head",
        account=account,
    )

    budget = FutureBudget.objects.create(
        account=account,
        source_fy=source_fy,
        target_fy=target_fy,
    )

    line = FutureBudgetLine.objects.create(
        future_budget=budget,
        account_head=head,
        system_suggested=Decimal("1000.00"),
    )

    unit = Unit.objects.create(
        code="G23-A",
        name="G23 Allocation Unit",
    )

    section = InternalSection.objects.create(
        code="G23-S",
        name="G23 Allocation Section",
    )

    user = get_user_model().objects.create_user(
        username="g23_allocator"
    )

    return line, unit, section, user


def test_unit_allocation_reconciles_exactly(allocation_context):
    line, unit, section, user = allocation_context

    FutureBudgetAllocationService.allocate(
        line,
        "1000.00",
        user,
        unit=unit,
    )

    result = FutureBudgetAllocationService.reconcile(line)

    assert result["allocated"] == Decimal("1000.00")
    assert result["difference"] == Decimal("0.00")
    assert result["status"] == "RECONCILED"


def test_under_and_over_allocation_are_unreconciled(allocation_context):
    line, unit, section, user = allocation_context

    FutureBudgetAllocationService.allocate(
        line,
        "900.00",
        user,
        unit=unit,
    )

    result = FutureBudgetAllocationService.reconcile(line)

    assert result["difference"] == Decimal("100.00")
    assert result["status"] == "UNRECONCILED"

    second_unit = Unit.objects.create(
        code="G23-B",
        name="G23 Second Unit",
    )

    FutureBudgetAllocationService.allocate(
        line,
        "200.00",
        user,
        unit=second_unit,
    )

    result = FutureBudgetAllocationService.reconcile(line)

    assert result["difference"] == Decimal("-100.00")
    assert result["status"] == "UNRECONCILED"


def test_section_and_combined_allocation_are_supported(allocation_context):
    line, unit, section, user = allocation_context

    FutureBudgetAllocationService.allocate(
        line,
        "250.00",
        user,
        internal_section=section,
    )

    FutureBudgetAllocationService.allocate(
        line,
        "750.00",
        user,
        unit=unit,
        internal_section=section,
    )

    result = FutureBudgetAllocationService.reconcile(line)

    assert result["status"] == "RECONCILED"


def test_allocation_does_not_change_parent_amount(allocation_context):
    line, unit, section, user = allocation_context

    original = line.system_suggested

    FutureBudgetAllocationService.allocate(
        line,
        "100.00",
        user,
        unit=unit,
    )

    line.refresh_from_db()

    assert line.system_suggested == original
    assert line.user_proposed is None
    assert line.approved_amount is None


def test_allocation_requires_organisation_and_positive_amount(allocation_context):
    line, unit, section, user = allocation_context

    with pytest.raises(ValidationError):
        FutureBudgetAllocationService.allocate(
            line,
            "10.00",
            user,
        )

    with pytest.raises(ValidationError):
        FutureBudgetAllocationService.allocate(
            line,
            "0.00",
            user,
            unit=unit,
        )

    with pytest.raises(ValidationError):
        FutureBudgetAllocationService.allocate(
            line,
            "-1.00",
            user,
            unit=unit,
        )


def test_duplicate_organisation_combination_is_rejected_by_database(
    allocation_context,
):
    line, unit, section, user = allocation_context

    FutureBudgetAllocationService.allocate(
        line,
        "100.00",
        user,
        unit=unit,
        internal_section=section,
    )

    with pytest.raises(Exception):
        FutureBudgetAllocationService.allocate(
            line,
            "100.00",
            user,
            unit=unit,
            internal_section=section,
        )