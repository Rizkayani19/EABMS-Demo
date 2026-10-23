from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from core.future_budget_inflow_proposal import get_user_proposed_inflow
from core.future_budget_management_models import FutureBudgetDecisionHistory
from core.future_budget_workflow import FutureBudgetWorkflowService
from core.models import Account, AccountHead, FinancialYear, FutureBudget, FutureBudgetLine


@pytest.mark.django_db
def make_inflow_line(username="inflow_audit", head_type=AccountHead.HeadType.INFLOW):
    user = get_user_model().objects.create_user(username=username)
    account = Account.objects.create(code=f"AUD-{username.upper()}", name=f"{username} account")
    target = FinancialYear.objects.create(
        code="FY-2040-41", name="2040-41", start_date=date(2040, 7, 1), end_date=date(2041, 6, 30)
    )
    source = FinancialYear.objects.create(
        code="FY-2039-40", name="2039-40", start_date=date(2039, 7, 1), end_date=date(2040, 6, 30)
    )
    head = AccountHead.objects.create(name="Audit Inflow Head", account=account, head_type=head_type)
    budget = FutureBudget.objects.create(account=account, target_fy=target, source_fy=source)
    line = FutureBudgetLine.objects.create(
        future_budget=budget,
        account_head=head,
        system_suggested=Decimal("400.00"),
    )
    return user, line


@pytest.mark.django_db
def test_inflow_proposal_records_same_decision_history_shape_as_outflow():
    user, line = make_inflow_line()

    FutureBudgetWorkflowService.propose_inflow(line, Decimal("500.00"), user, "Funding requirement")
    history = FutureBudgetDecisionHistory.objects.get(future_budget_line=line)

    assert history.action == FutureBudgetDecisionHistory.Action.PROPOSE
    assert history.previous_proposed_inflow is None
    assert history.new_proposed_inflow == Decimal("500.00")
    assert history.previous_approved_inflow is None
    assert history.new_approved_inflow is None
    assert history.system_suggested_snapshot == Decimal("400.00")
    assert history.actor_id == user.id


@pytest.mark.django_db
def test_inflow_approval_requires_proposal_and_records_approval_snapshot():
    user, line = make_inflow_line("inflow_approval")

    with pytest.raises(ValidationError):
        FutureBudgetWorkflowService.approve_inflow(line, user)

    FutureBudgetWorkflowService.propose_inflow(line, Decimal("550.00"), user)
    FutureBudgetWorkflowService.approve_inflow(line, user)
    line.refresh_from_db()

    assert get_user_proposed_inflow(line) == Decimal("550.00")
    assert line.approved_inflow_amount == Decimal("550.00")

    actions = list(
        FutureBudgetDecisionHistory.objects
        .filter(future_budget_line=line)
        .order_by("created_at", "id")
    )
    assert [item.action for item in actions] == [
        FutureBudgetDecisionHistory.Action.PROPOSE,
        FutureBudgetDecisionHistory.Action.APPROVE,
    ]
    assert actions[1].previous_proposed_inflow == Decimal("550.00")
    assert actions[1].new_proposed_inflow == Decimal("550.00")
    assert actions[1].previous_approved_inflow is None
    assert actions[1].new_approved_inflow == Decimal("550.00")


@pytest.mark.django_db
def test_negative_inflow_proposal_creates_no_history():
    user, line = make_inflow_line("inflow_negative")

    with pytest.raises(ValidationError):
        FutureBudgetWorkflowService.propose_inflow(line, Decimal("-1.00"), user)

    assert FutureBudgetDecisionHistory.objects.filter(future_budget_line=line).count() == 0


@pytest.mark.django_db
def test_inflow_reopen_preserves_proposal_and_audits_approval_removal():
    user, line = make_inflow_line("inflow_reopen")

    FutureBudgetWorkflowService.propose_inflow(line, Decimal("600.00"), user)
    FutureBudgetWorkflowService.approve_inflow(line, user)
    FutureBudgetWorkflowService.reopen_inflow(line, user, "Recheck funding")
    line.refresh_from_db()

    assert get_user_proposed_inflow(line) == Decimal("600.00")
    assert line.approved_inflow_amount is None

    reopened = FutureBudgetDecisionHistory.objects.get(
        future_budget_line=line,
        action=FutureBudgetDecisionHistory.Action.REOPEN,
    )
    assert reopened.previous_proposed_inflow == Decimal("600.00")
    assert reopened.new_proposed_inflow == Decimal("600.00")
    assert reopened.previous_approved_inflow == Decimal("600.00")
    assert reopened.new_approved_inflow is None
