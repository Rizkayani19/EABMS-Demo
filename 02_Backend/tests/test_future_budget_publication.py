from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from core.future_budget_inflow_proposal import set_user_proposed_inflow
from core.future_budget_publication import FutureBudgetPublicationService
from core.budget_inflow_models import BudgetInflowLine
from core.models import (
    Account,
    AccountHead,
    Budget,
    BudgetLine,
    BudgetType,
    FinancialYear,
    FutureBudget,
    FutureBudgetLine,
)


def make_year(code, start_year):
    return FinancialYear.objects.create(
        code=code,
        name=code,
        start_date=date(start_year, 7, 1),
        end_date=date(start_year + 1, 6, 30),
    )


def make_budget_type():
    return BudgetType.objects.create(code="ROUTINE", name="Routine")


def make_future_budget(status=FutureBudget.Status.PROPOSED):
    account = Account.objects.create(code="PUB-NGL", name="Publication NGL")
    source_fy = make_year("2034-35", 2034)
    target_fy = make_year("2035-36", 2035)
    budget_type = make_budget_type()
    outflow_head = AccountHead.objects.create(
        account=account,
        name="Salaries",
        head_type=AccountHead.HeadType.OUTFLOW,
    )
    inflow_head = AccountHead.objects.create(
        account=account,
        name="HQO Transfer",
        head_type=AccountHead.HeadType.INFLOW,
    )
    future = FutureBudget.objects.create(
        account=account,
        source_fy=source_fy,
        target_fy=target_fy,
        status=status,
    )
    outflow_line = FutureBudgetLine.objects.create(
        future_budget=future,
        account_head=outflow_head,
        budget_type=budget_type,
        user_proposed=Decimal("46000000.00"),
    )
    inflow_line = FutureBudgetLine.objects.create(
        future_budget=future,
        account_head=inflow_head,
        budget_type=budget_type,
    )
    set_user_proposed_inflow(inflow_line, Decimal("50000000.00"))
    inflow_line.save(update_fields=["suggestion_breakdown", "updated_at"])
    return future, outflow_line, inflow_line


@pytest.mark.django_db
def test_publication_creates_target_budget_and_publishes_approved_values():
    user = get_user_model().objects.create_user(username="publication_approver")
    future, outflow_line, inflow_line = make_future_budget()

    target = FutureBudgetPublicationService.publish(future, user)

    future.refresh_from_db()
    outflow_line.refresh_from_db()
    inflow_line.refresh_from_db()

    assert future.status == FutureBudget.Status.APPROVED
    assert outflow_line.approved_amount == Decimal("46000000.00")
    assert inflow_line.approved_inflow_amount == Decimal("50000000.00")
    assert Budget.objects.filter(pk=target.pk, account=future.account, financial_year=future.target_fy).exists()
    assert Budget.objects.filter(pk=target.pk, status=Budget.Status.APPROVED).exists()
    assert BudgetLine.objects.filter(
        budget=target,
        account_head=outflow_line.account_head,
        amount=Decimal("46000000.00"),
    ).exists()
    assert BudgetInflowLine.objects.filter(
        budget=target,
        account_head=inflow_line.account_head,
        amount=Decimal("50000000.00"),
    ).exists()


@pytest.mark.django_db
def test_publication_rejects_existing_target_budget_without_changes():
    user = get_user_model().objects.create_user(username="publication_duplicate")
    future, outflow_line, _ = make_future_budget()
    existing = Budget.objects.create(
        account=future.account,
        financial_year=future.target_fy,
        status=Budget.Status.DRAFT,
        created_by=user,
    )

    with pytest.raises(ValidationError):
        FutureBudgetPublicationService.publish(future, user)

    future.refresh_from_db()
    outflow_line.refresh_from_db()

    assert future.status == FutureBudget.Status.PROPOSED
    assert outflow_line.approved_amount is None
    assert Budget.objects.filter(pk=existing.pk).count() == 1
    assert BudgetLine.objects.filter(budget=existing).count() == 0
    assert BudgetInflowLine.objects.filter(budget=existing).count() == 0


@pytest.mark.django_db
def test_publication_rejects_missing_inflow_management_proposal():
    user = get_user_model().objects.create_user(username="publication_missing_inflow")
    future, outflow_line, inflow_line = make_future_budget()
    set_user_proposed_inflow(inflow_line, None)
    inflow_line.save(update_fields=["suggestion_breakdown", "updated_at"])

    with pytest.raises(ValidationError, match="Management inflow proposal is missing"):
        FutureBudgetPublicationService.publish(future, user)

    future.refresh_from_db()
    outflow_line.refresh_from_db()

    assert future.status == FutureBudget.Status.PROPOSED
    assert outflow_line.approved_amount is None
    assert Budget.objects.filter(account=future.account, financial_year=future.target_fy).count() == 0


@pytest.mark.django_db
def test_publication_is_atomic_when_a_management_proposal_is_missing():
    user = get_user_model().objects.create_user(username="publication_atomic")
    future, outflow_line, inflow_line = make_future_budget()
    set_user_proposed_inflow(inflow_line, None)
    inflow_line.save(update_fields=["suggestion_breakdown", "updated_at"])

    with pytest.raises(ValidationError):
        FutureBudgetPublicationService.publish(future, user)

    future.refresh_from_db()
    outflow_line.refresh_from_db()

    assert future.status == FutureBudget.Status.PROPOSED
    assert outflow_line.approved_amount is None
    assert Budget.objects.filter(account=future.account, financial_year=future.target_fy).count() == 0
