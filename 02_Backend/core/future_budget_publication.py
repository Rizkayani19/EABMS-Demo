from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from .budget_inflow_models import BudgetInflowLine
from .future_budget_inflow_proposal import get_user_proposed_inflow, set_user_proposed_inflow
from .future_budget_management_models import FutureBudgetDecisionHistory
from .models import Budget, BudgetLine, FutureBudget, FutureBudgetLine

ZERO = Decimal('0.00')


class FutureBudgetPublicationService:
    """Publish a Future Budget into the canonical target-year Budget, preserving both sides."""

    @classmethod
    @transaction.atomic
    def publish(cls, future_budget, actor, overwrite_existing=False):
        if future_budget is None or not future_budget.pk:
            raise ValidationError('A persisted Future Budget is required.')
        if actor is None or not getattr(actor, 'is_authenticated', False):
            raise ValidationError('An authenticated actor is required to publish a Future Budget.')
        if future_budget.status not in (FutureBudget.Status.PROPOSED, FutureBudget.Status.APPROVED):
            raise ValidationError('Only a Proposed or Approved Future Budget can be published.')
        if future_budget.source_fy_id == future_budget.target_fy_id:
            raise ValidationError('Source and target Financial Years must be different.')

        lines = list(
            FutureBudgetLine.objects.select_related(
                'account_head', 'major_head', 'sub_head', 'budget_type'
            ).filter(future_budget=future_budget).order_by(
                'major_head__display_order', 'major_head__code', 'account_head__display_order', 'account_head__name', 'pk'
            )
        )
        if not lines:
            raise ValidationError('The Future Budget has no planning lines to publish.')

        for line in lines:
            if line.major_head and not line.account_head:
                proposed_inflow = get_user_proposed_inflow(line)
                if line.user_proposed is None:
                    line.user_proposed = line.system_suggested or ZERO

                if line.user_proposed < ZERO:
                    raise ValidationError(
                        f"Management outflow proposal cannot be negative for Sub-Fund '{line.major_head.name}'."
                    )
                if proposed_inflow is not None and proposed_inflow < ZERO:
                    raise ValidationError(
                        f"Management inflow proposal cannot be negative for Sub-Fund '{line.major_head.name}'."
                    )
            else:
                can_out = line.account_head.head_type in ('OUTFLOW', 'BOTH')
                can_in = line.account_head.head_type in ('INFLOW', 'BOTH')
                proposed_inflow = get_user_proposed_inflow(line)

                # For heads where head_type is BOTH, if inflow proposal is absent, default to ZERO safely
                if can_in and line.account_head.head_type == 'BOTH' and proposed_inflow is None:
                    set_user_proposed_inflow(line, ZERO)
                    proposed_inflow = ZERO

                # If user proposed outflow is absent for an outflow/both head, default to system suggested
                if can_out and line.user_proposed is None:
                    line.user_proposed = line.system_suggested or ZERO

                if can_out and line.user_proposed < ZERO:
                    raise ValidationError(
                        f"Management outflow proposal cannot be negative for '{line.account_head.name}'."
                    )
                if can_in and proposed_inflow is None:
                    raise ValidationError(
                        f"Management inflow proposal is missing for Account Head '{line.account_head.name}'."
                    )
                if can_in and proposed_inflow < ZERO:
                    raise ValidationError(
                        f"Management inflow proposal cannot be negative for '{line.account_head.name}'."
                    )

        existing = Budget.objects.filter(
            account=future_budget.account,
            financial_year=future_budget.target_fy,
        ).first()
        if existing is not None and not overwrite_existing:
            raise ValidationError(
                f'A target Budget already exists for {future_budget.account.code} / '
                f'{future_budget.target_fy.code} (Budget #{existing.pk}). Publication was not performed.'
            )

        if existing is not None and overwrite_existing:
            target = existing
            target.status = Budget.Status.APPROVED
            target.budget_allocation_basis = future_budget.budget_allocation_basis
            target.reference = f'Published from Future Budget #{future_budget.pk}'
            target.remarks = future_budget.remarks
            target.updated_by = actor
            target.save(update_fields=['status', 'budget_allocation_basis', 'reference', 'remarks', 'updated_by', 'updated_at'])
            target.lines.all().delete()
            target.inflow_lines.all().delete()
        else:
            target = Budget.objects.create(
                account=future_budget.account,
                financial_year=future_budget.target_fy,
                budget_allocation_basis=future_budget.budget_allocation_basis,
                status=Budget.Status.APPROVED,
                reference=f'Published from Future Budget #{future_budget.pk}',
                remarks=future_budget.remarks,
                created_by=actor,
                updated_by=actor,
            )

        from .models import BudgetType
        default_budget_type = BudgetType.objects.filter(code='ROUTINE').first() or BudgetType.objects.first()

        for line in lines:
            previous_proposed = line.user_proposed
            previous_approved = line.approved_amount
            previous_proposed_inflow = get_user_proposed_inflow(line)
            previous_approved_inflow = line.approved_inflow_amount
            approved = None
            approved_inflow = None
            line_btype = line.budget_type or default_budget_type

            if line.major_head and not line.account_head:
                if line.user_proposed is not None:
                    approved = Decimal(str(line.user_proposed))
                    line.approved_amount = approved
                    if approved > ZERO:
                        BudgetLine.objects.create(
                            budget=target,
                            account_head=None,
                            major_head=line.major_head,
                            sub_head=None,
                            unit=None,
                            budget_type=line_btype,
                            amount=approved,
                            remarks=line.remarks or 'Published from approved Future Budget (Sub-Fund).',
                        )

                proposed_inflow = get_user_proposed_inflow(line)
                if proposed_inflow is not None:
                    approved_inflow = Decimal(str(proposed_inflow))
                    if approved_inflow > ZERO:
                        BudgetInflowLine.objects.create(
                            budget=target,
                            account_head=None,
                            major_head=line.major_head,
                            unit=None,
                            budget_type=line_btype,
                            amount=approved_inflow,
                            remarks=line.remarks or 'Published from approved Future Budget inflow (Sub-Fund).',
                        )
                    line.approved_inflow_amount = approved_inflow
            else:
                if line.account_head.head_type in ('OUTFLOW', 'BOTH'):
                    approved = Decimal(str(line.user_proposed))
                    line.approved_amount = approved
                    if approved > ZERO:
                        BudgetLine.objects.create(
                            budget=target,
                            account_head=line.account_head,
                            major_head=line.major_head or line.account_head.major_head,
                            sub_head=line.sub_head or line.account_head.sub_head,
                            unit=None,
                            budget_type=line_btype,
                            amount=approved,
                            remarks=line.remarks or 'Published from approved Future Budget.',
                        )

                if line.account_head.head_type in ('INFLOW', 'BOTH'):
                    proposed_inflow = get_user_proposed_inflow(line)
                    approved_inflow = Decimal(str(proposed_inflow or ZERO))
                    if approved_inflow > ZERO:
                        BudgetInflowLine.objects.create(
                            budget=target,
                            account_head=line.account_head,
                            major_head=line.account_head.major_head,
                            unit=None,
                            budget_type=line_btype,
                            amount=approved_inflow,
                            remarks=line.remarks or 'Published from approved Future Budget inflow.',
                        )
                    line.approved_inflow_amount = approved_inflow

            line.save(update_fields=['user_proposed', 'suggestion_breakdown', 'approved_amount', 'approved_inflow_amount', 'updated_at'])

            FutureBudgetDecisionHistory.objects.create(
                future_budget_line=line,
                action=FutureBudgetDecisionHistory.Action.APPROVE,
                actor=actor,
                previous_proposed=previous_proposed,
                new_proposed=line.user_proposed,
                previous_proposed_inflow=previous_proposed_inflow,
                new_proposed_inflow=get_user_proposed_inflow(line),
                previous_approved=previous_approved,
                new_approved=approved if approved is not None else previous_approved,
                previous_approved_inflow=previous_approved_inflow,
                new_approved_inflow=approved_inflow if approved_inflow is not None else previous_approved_inflow,
                system_suggested_snapshot=line.system_suggested,
                remarks='Future Budget approved and published to target-year Budget.',
            )

        future_budget.status = FutureBudget.Status.APPROVED
        future_budget.save(update_fields=['status', 'updated_at'])
        return target
