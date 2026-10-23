from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from core.future_budget_management_models import FutureBudgetDecisionHistory
from core.future_budget_workflow import FutureBudgetWorkflowService
from core.models import Account, AccountHead, FinancialYear, FutureBudget, FutureBudgetLine


@pytest.mark.django_db
def make_line(username, account_name, fy_name, head_name, suggested):
    user = get_user_model().objects.create_user(username=username)

    account = Account.objects.create(
        code=f"TEST-{username.upper()}",
        name=account_name,
    )

    start_year = int(fy_name[:4])

    target_fy = FinancialYear.objects.create(
        code=f"FY-{start_year}-{(start_year + 1) % 100:02d}",
        name=fy_name,
        start_date=date(start_year, 7, 1),
        end_date=date(start_year + 1, 6, 30),
    )

    source_start_year = start_year - 1
    source_fy = FinancialYear.objects.create(
        code=f"FY-{source_start_year}-{(source_start_year + 1) % 100:02d}",
        name=f"{source_start_year}-{(source_start_year + 1) % 100:02d}",
        start_date=date(source_start_year, 7, 1),
        end_date=date(source_start_year + 1, 6, 30),
    )

    head = AccountHead.objects.create(
        name=head_name,
        account=account,
    )

    budget = FutureBudget.objects.create(
        account=account,
        target_fy=target_fy,
        source_fy=source_fy,
    )

    line = FutureBudgetLine.objects.create(
        future_budget=budget,
        account_head=head,
        system_suggested=suggested,
    )

    return user, line


@pytest.mark.django_db
def test_propose_records_immutable_decision_history():
    user, line = make_line("g23_proposer", "G23 Workflow Account", "2030-31", "G23 Workflow Head", Decimal("100.00"))

    FutureBudgetWorkflowService.propose(line, Decimal("125.00"), user, "Need", "Proposal")

    history = FutureBudgetDecisionHistory.objects.get(future_budget_line=line)
    assert history.action == FutureBudgetDecisionHistory.Action.PROPOSE
    assert history.previous_proposed is None
    assert history.new_proposed == Decimal("125.00")
    assert history.previous_approved is None
    assert history.new_approved is None
    assert history.system_suggested_snapshot == Decimal("100.00")
    assert history.actor_id == user.id


@pytest.mark.django_db
def test_approval_requires_proposal_and_records_snapshot():
    user, line = make_line("g23_approver", "G23 Approval Account", "2031-32", "G23 Approval Head", Decimal("200.00"))

    with pytest.raises(ValidationError):
        FutureBudgetWorkflowService.approve(line, user)

    FutureBudgetWorkflowService.propose(line, Decimal("225.00"), user)
    FutureBudgetWorkflowService.approve(line, user)
    line.refresh_from_db()

    assert line.system_suggested == Decimal("200.00")
    assert line.user_proposed == Decimal("225.00")
    assert line.approved_amount == Decimal("225.00")

    actions = list(
        FutureBudgetDecisionHistory.objects
        .filter(future_budget_line=line)
        .order_by("created_at", "id")
    )

    assert [item.action for item in actions] == [
        FutureBudgetDecisionHistory.Action.PROPOSE,
        FutureBudgetDecisionHistory.Action.APPROVE,
    ]

    assert actions[1].previous_proposed == Decimal("225.00")
    assert actions[1].new_approved == Decimal("225.00")
    assert actions[1].system_suggested_snapshot == Decimal("200.00")


@pytest.mark.django_db
def test_negative_proposal_is_rejected_without_history():
    user, line = make_line("g23_negative", "G23 Negative Account", "2032-33", "G23 Negative Head", Decimal("50.00"))

    with pytest.raises(ValidationError):
        FutureBudgetWorkflowService.propose(line, Decimal("-1.00"), user)

    assert FutureBudgetDecisionHistory.objects.filter(future_budget_line=line).count() == 0


@pytest.mark.django_db
def test_reject_records_rejection_and_clears_current_decision():
    user, line = make_line("g23_reject", "G23 Reject Account", "2033-34", "G23 Reject Head", Decimal("75.00"))

    FutureBudgetWorkflowService.propose(line, Decimal("90.00"), user)
    FutureBudgetWorkflowService.reject_proposal(line, user, "Not required")
    line.refresh_from_db()

    assert line.system_suggested == Decimal("75.00")
    assert line.user_proposed is None
    assert line.approved_amount is None

    rejection = FutureBudgetDecisionHistory.objects.get(
        future_budget_line=line,
        action=FutureBudgetDecisionHistory.Action.REJECT,
    )

    assert rejection.previous_proposed == Decimal("90.00")
    assert rejection.new_proposed is None
    assert rejection.reason == "Not required"
    assert rejection.system_suggested_snapshot == Decimal("75.00")


@pytest.mark.django_db
def test_reopen_records_history_and_preserves_proposal():
    user, line = make_line("g23_reopen", "G23 Reopen Account", "2034-35", "G23 Reopen Head", Decimal("80.00"))

    FutureBudgetWorkflowService.propose(line, Decimal("95.00"), user)
    FutureBudgetWorkflowService.approve(line, user)
    FutureBudgetWorkflowService.reopen(line, user, "New requirement review")
    line.refresh_from_db()

    assert line.system_suggested == Decimal("80.00")
    assert line.user_proposed == Decimal("95.00")
    assert line.approved_amount is None

    reopened = FutureBudgetDecisionHistory.objects.get(
        future_budget_line=line,
        action=FutureBudgetDecisionHistory.Action.REOPEN,
    )

    assert reopened.previous_approved == Decimal("95.00")
    assert reopened.new_approved is None
    assert reopened.reason == "New requirement review"
