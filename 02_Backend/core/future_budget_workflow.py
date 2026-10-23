from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from .future_budget_inflow_proposal import get_user_proposed_inflow, set_user_proposed_inflow
from .models import FutureBudgetLine
from .future_budget_management_models import FutureBudgetDecisionHistory


ZERO = Decimal("0.00")


class FutureBudgetWorkflowService:
    """Canonical mutation boundary for Future Budget management decisions."""

    @staticmethod
    def _validate_line(line: FutureBudgetLine) -> FutureBudgetLine:
        if line is None or not line.pk:
            raise ValidationError("A persisted Future Budget line is required.")
        if not line.future_budget_id or not (line.account_head_id or line.major_head_id):
            raise ValidationError("Future Budget line must have valid budget and account-head or sub-fund ownership.")
        return line

    @staticmethod
    def _record(
        line,
        action,
        actor,
        previous_proposed,
        new_proposed,
        previous_approved,
        new_approved,
        reason="",
        remarks="",
        previous_proposed_inflow=None,
        new_proposed_inflow=None,
        previous_approved_inflow=None,
        new_approved_inflow=None,
    ):
        return FutureBudgetDecisionHistory.objects.create(
            future_budget_line=line,
            action=action,
            actor=actor,
            previous_proposed=previous_proposed,
            new_proposed=new_proposed,
            previous_proposed_inflow=previous_proposed_inflow,
            new_proposed_inflow=new_proposed_inflow,
            previous_approved=previous_approved,
            new_approved=new_approved,
            previous_approved_inflow=previous_approved_inflow,
            new_approved_inflow=new_approved_inflow,
            system_suggested_snapshot=line.system_suggested,
            reason=reason,
            remarks=remarks,
        )

    @staticmethod
    def _require_actor(actor):
        if actor is None or not getattr(actor, "is_authenticated", False):
            raise ValidationError("An authenticated actor is required to change a Future Budget decision.")

    @classmethod
    @transaction.atomic
    def propose(cls, line, amount, actor, justification="", remarks=""):
        line = cls._validate_line(line)
        cls._require_actor(actor)
        amount = Decimal(str(amount))
        if amount < ZERO:
            raise ValidationError("Management proposed amount cannot be negative.")
        previous_proposed = line.user_proposed
        previous_approved = line.approved_amount
        line.user_proposed = amount
        if justification:
            line.justification = justification
        if remarks:
            line.remarks = remarks
        line.save(update_fields=["user_proposed", "justification", "remarks", "updated_at"])
        cls._record(
            line, FutureBudgetDecisionHistory.Action.PROPOSE, actor,
            previous_proposed, line.user_proposed,
            previous_approved, line.approved_amount,
            remarks=remarks,
        )
        return line

    @classmethod
    @transaction.atomic
    def propose_inflow(cls, line, amount, actor, justification="", remarks=""):
        """Record a management inflow proposal with the same immutable decision audit used for outflow."""
        line = cls._validate_line(line)
        cls._require_actor(actor)
        if line.account_head and line.account_head.head_type not in ("INFLOW", "BOTH"):
            raise ValidationError("This Future Budget line does not support inflow proposals.")
        amount = Decimal(str(amount))
        if amount < ZERO:
            raise ValidationError("Management proposed inflow cannot be negative.")
        previous_proposed_inflow = get_user_proposed_inflow(line)
        previous_approved_inflow = line.approved_inflow_amount
        set_user_proposed_inflow(line, amount)
        if justification:
            line.justification = justification
        if remarks:
            line.remarks = remarks
        line.save(update_fields=["suggestion_breakdown", "justification", "remarks", "updated_at"])
        cls._record(
            line, FutureBudgetDecisionHistory.Action.PROPOSE, actor,
            line.user_proposed, line.user_proposed,
            line.approved_amount, line.approved_amount,
            remarks=remarks,
            previous_proposed_inflow=previous_proposed_inflow,
            new_proposed_inflow=get_user_proposed_inflow(line),
            previous_approved_inflow=previous_approved_inflow,
            new_approved_inflow=line.approved_inflow_amount,
        )
        return line

    @classmethod
    @transaction.atomic
    def approve(cls, line, actor, amount=None, remarks=""):
        line = cls._validate_line(line)
        cls._require_actor(actor)
        if line.user_proposed is None and amount is None:
            raise ValidationError("An explicit management proposal is required before approval.")
        approved = line.user_proposed if amount is None else Decimal(str(amount))
        if approved < ZERO:
            raise ValidationError("Approved amount cannot be negative.")
        previous_proposed = line.user_proposed
        previous_approved = line.approved_amount
        line.approved_amount = approved
        if remarks:
            line.remarks = remarks
        line.save(update_fields=["approved_amount", "remarks", "updated_at"])
        cls._record(
            line, FutureBudgetDecisionHistory.Action.APPROVE, actor,
            previous_proposed, line.user_proposed,
            previous_approved, line.approved_amount,
            remarks=remarks,
        )
        return line

    @classmethod
    @transaction.atomic
    def approve_inflow(cls, line, actor, amount=None, remarks=""):
        """Approve a management inflow proposal and retain a complete immutable audit snapshot."""
        line = cls._validate_line(line)
        cls._require_actor(actor)
        if line.account_head and line.account_head.head_type not in ("INFLOW", "BOTH"):
            raise ValidationError("This Future Budget line does not support inflow approval.")
        proposed = get_user_proposed_inflow(line)
        if proposed is None and amount is None:
            raise ValidationError("An explicit management inflow proposal is required before approval.")
        approved = proposed if amount is None else Decimal(str(amount))
        if approved < ZERO:
            raise ValidationError("Approved inflow cannot be negative.")
        previous_proposed_inflow = proposed
        previous_approved_inflow = line.approved_inflow_amount
        set_user_proposed_inflow(line, approved)
        line.approved_inflow_amount = approved
        if remarks:
            line.remarks = remarks
        line.save(update_fields=["suggestion_breakdown", "approved_inflow_amount", "remarks", "updated_at"])
        cls._record(
            line, FutureBudgetDecisionHistory.Action.APPROVE, actor,
            line.user_proposed, line.user_proposed,
            line.approved_amount, line.approved_amount,
            remarks=remarks,
            previous_proposed_inflow=previous_proposed_inflow,
            new_proposed_inflow=get_user_proposed_inflow(line),
            previous_approved_inflow=previous_approved_inflow,
            new_approved_inflow=line.approved_inflow_amount,
        )
        return line

    @classmethod
    @transaction.atomic
    def reject_proposal(cls, line, actor, reason=""):
        line = cls._validate_line(line)
        cls._require_actor(actor)
        if line.user_proposed is None:
            raise ValidationError("There is no current management proposal to reject.")
        previous_proposed = line.user_proposed
        previous_approved = line.approved_amount
        line.user_proposed = None
        line.approved_amount = None
        line.remarks = reason or line.remarks
        line.save(update_fields=["user_proposed", "approved_amount", "remarks", "updated_at"])
        cls._record(
            line, FutureBudgetDecisionHistory.Action.REJECT, actor,
            previous_proposed, line.user_proposed,
            previous_approved, line.approved_amount,
            reason=reason, remarks=reason,
        )
        return line

    @classmethod
    @transaction.atomic
    def reject_inflow_proposal(cls, line, actor, reason=""):
        line = cls._validate_line(line)
        cls._require_actor(actor)
        proposed = get_user_proposed_inflow(line)
        if (line.account_head and line.account_head.head_type not in ("INFLOW", "BOTH")) or proposed is None:
            raise ValidationError("There is no current management inflow proposal to reject.")
        previous_approved = line.approved_inflow_amount
        set_user_proposed_inflow(line, None)
        line.approved_inflow_amount = None
        line.remarks = reason or line.remarks
        line.save(update_fields=["suggestion_breakdown", "approved_inflow_amount", "remarks", "updated_at"])
        cls._record(
            line, FutureBudgetDecisionHistory.Action.REJECT, actor,
            line.user_proposed, line.user_proposed,
            line.approved_amount, line.approved_amount,
            reason=reason, remarks=reason,
            previous_proposed_inflow=proposed,
            new_proposed_inflow=None,
            previous_approved_inflow=previous_approved,
            new_approved_inflow=None,
        )
        return line

    @classmethod
    @transaction.atomic
    def reopen(cls, line, actor, reason=""):
        line = cls._validate_line(line)
        cls._require_actor(actor)
        if line.approved_amount is None:
            raise ValidationError("There is no approved amount to reopen.")
        previous_proposed = line.user_proposed
        previous_approved = line.approved_amount
        line.approved_amount = None
        line.remarks = reason or line.remarks
        line.save(update_fields=["approved_amount", "remarks", "updated_at"])
        cls._record(
            line, FutureBudgetDecisionHistory.Action.REOPEN, actor,
            previous_proposed, line.user_proposed,
            previous_approved, line.approved_amount,
            reason=reason, remarks=reason,
        )
        return line

    @classmethod
    @transaction.atomic
    def reopen_inflow(cls, line, actor, reason=""):
        line = cls._validate_line(line)
        cls._require_actor(actor)
        if (line.account_head and line.account_head.head_type not in ("INFLOW", "BOTH")) or line.approved_inflow_amount is None:
            raise ValidationError("There is no approved inflow amount to reopen.")
        previous_proposed_inflow = get_user_proposed_inflow(line)
        previous_approved_inflow = line.approved_inflow_amount
        line.approved_inflow_amount = None
        line.remarks = reason or line.remarks
        line.save(update_fields=["approved_inflow_amount", "remarks", "updated_at"])
        cls._record(
            line, FutureBudgetDecisionHistory.Action.REOPEN, actor,
            line.user_proposed, line.user_proposed,
            line.approved_amount, line.approved_amount,
            reason=reason, remarks=reason,
            previous_proposed_inflow=previous_proposed_inflow,
            new_proposed_inflow=previous_proposed_inflow,
            previous_approved_inflow=previous_approved_inflow,
            new_approved_inflow=None,
        )
        return line
