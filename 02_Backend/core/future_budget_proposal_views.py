from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction as db_transaction
from django.shortcuts import get_object_or_404, redirect
from django.views import View

from .future_budget_inflow_proposal import get_user_proposed_inflow
from .future_budget_workflow import FutureBudgetWorkflowService
from .models import FutureBudget, FutureBudgetLine, UserProfile


MANAGEMENT_ROLES = (UserProfile.Role.ADMINISTRATOR, UserProfile.Role.MANAGEMENT)


def _is_inflow_side(line):
    if line.account_head:
        return line.account_head.head_type in ('INFLOW', 'BOTH')
    return True


def _is_outflow_side(line):
    if line.account_head:
        return line.account_head.head_type in ('OUTFLOW', 'BOTH')
    return True


class FutureBudgetLineProposalView(LoginRequiredMixin, View):
    """Set management outflow and/or inflow proposal for one Draft future-budget line."""

    @db_transaction.atomic
    def post(self, request, pk):
        profile = getattr(request.user, 'profile', None)
        if not profile or profile.role not in MANAGEMENT_ROLES:
            raise PermissionDenied('Only Management or Administrator may enter a future-budget proposal.')

        line = get_object_or_404(
            FutureBudgetLine.objects.select_related('future_budget', 'account_head'),
            pk=pk,
            future_budget__account=request.account,
        )
        budget = line.future_budget
        if budget.status not in (FutureBudget.Status.DRAFT, FutureBudget.Status.PROPOSED):
            raise PermissionDenied('Management proposals can only be changed while the future budget is Draft or Proposed.')

        justification = (request.POST.get('justification') or '').strip()
        remarks = (request.POST.get('remarks') or '').strip()
        has_outflow_field = 'user_proposed' in request.POST
        has_inflow_field = 'proposed_inflow' in request.POST
        raw_amount = (request.POST.get('user_proposed') or '').strip()
        raw_inflow = (request.POST.get('proposed_inflow') or '').strip()

        try:
            amount = Decimal(raw_amount) if has_outflow_field and raw_amount else None
            inflow_amount = Decimal(raw_inflow) if has_inflow_field and raw_inflow else None
            if amount is not None and amount < 0:
                raise ValueError
            if inflow_amount is not None and inflow_amount < 0:
                raise ValueError
        except (InvalidOperation, TypeError, ValueError):
            messages.error(request, 'Enter valid non-negative proposed amount(s).')
            return redirect('core:future_budget_review', pk=budget.pk)

        try:
            if has_outflow_field:
                if not _is_outflow_side(line):
                    raise ValidationError('This Future Budget line does not support outflow proposals.')
                if amount is None:
                    if line.user_proposed is not None:
                        FutureBudgetWorkflowService.reject_proposal(
                            line, request.user, reason='Management outflow proposal cleared.'
                        )
                else:
                    FutureBudgetWorkflowService.propose(
                        line, amount, request.user,
                        justification=justification,
                        remarks=remarks,
                    )

            if has_inflow_field:
                if not _is_inflow_side(line):
                    raise ValidationError('This Future Budget line does not support inflow proposals.')
                if inflow_amount is None:
                    if get_user_proposed_inflow(line) is not None:
                        FutureBudgetWorkflowService.reject_inflow_proposal(
                            line, request.user, reason='Management inflow proposal cleared.'
                        )
                else:
                    FutureBudgetWorkflowService.propose_inflow(
                        line, inflow_amount, request.user,
                        justification=justification,
                        remarks=remarks,
                    )
        except ValidationError as exc:
            messages.error(request, str(exc))
            return redirect('core:future_budget_review', pk=budget.pk)

        line.refresh_from_db(fields=['user_proposed', 'suggestion_breakdown'])
        if has_outflow_field or has_inflow_field:
            head_name = line.account_head.name if line.account_head else (line.major_head.name if line.major_head else f"Line #{line.pk}")
            messages.success(request, f'Management proposal for {head_name} saved.')
        return redirect('core:future_budget_review', pk=budget.pk)


class FutureBudgetClearProposalView(LoginRequiredMixin, View):
    """Clear unapproved outflow and inflow proposals during Draft review."""

    @db_transaction.atomic
    def post(self, request, pk):
        profile = getattr(request.user, 'profile', None)
        if not profile or profile.role not in MANAGEMENT_ROLES:
            raise PermissionDenied('Only Management or Administrator may clear a future-budget proposal.')
        line = get_object_or_404(
            FutureBudgetLine.objects.select_related('future_budget', 'account_head', 'major_head'),
            pk=pk,
            future_budget__account=request.account,
        )
        budget = line.future_budget
        if budget.status not in (FutureBudget.Status.DRAFT, FutureBudget.Status.PROPOSED):
            raise PermissionDenied('Only Draft or Proposed future budgets may be edited.')

        try:
            if _is_outflow_side(line) and line.user_proposed is not None:
                FutureBudgetWorkflowService.reject_proposal(
                    line, request.user, reason='Management outflow proposal cleared.'
                )
            if _is_inflow_side(line) and get_user_proposed_inflow(line) is not None:
                FutureBudgetWorkflowService.reject_inflow_proposal(
                    line, request.user, reason='Management inflow proposal cleared.'
                )
        except ValidationError as exc:
            messages.error(request, str(exc))
            return redirect('core:future_budget_review', pk=budget.pk)

        line.refresh_from_db(fields=['user_proposed', 'suggestion_breakdown', 'approved_amount', 'approved_inflow_amount'])
        head_name = line.account_head.name if line.account_head else (line.major_head.name if line.major_head else f"Line #{line.pk}")
        messages.success(request, f'Proposal cleared for {head_name}.')
        return redirect('core:future_budget_review', pk=budget.pk)


class FutureBudgetBulkCopySuggestedView(LoginRequiredMixin, View):
    """Copy system suggested outflow amounts to management proposals."""

    @db_transaction.atomic
    def post(self, request, pk):
        profile = getattr(request.user, 'profile', None)
        if not profile or profile.role not in MANAGEMENT_ROLES:
            raise PermissionDenied('Only Management or Administrator may update future-budget proposals.')
        budget = get_object_or_404(FutureBudget, pk=pk, account=request.account)
        if budget.status not in (FutureBudget.Status.DRAFT, FutureBudget.Status.PROPOSED):
            raise PermissionDenied('Proposals can only be updated while the budget is Draft or Proposed.')
        overwrite = request.POST.get('overwrite', '1') == '1'
        updated_count = 0
        for line in budget.lines.select_related('account_head'):
            if not _is_outflow_side(line):
                continue
            if not (overwrite or line.user_proposed is None):
                continue
            FutureBudgetWorkflowService.propose(
                line,
                line.system_suggested,
                request.user,
                justification=(line.justification or 'Copied from system suggested calculation.'),
                remarks=line.remarks,
            )
            updated_count += 1
        messages.success(request, f'Successfully copied System Suggested amounts to Management Proposed for {updated_count} account head(s).')
        return redirect('core:future_budget_review', pk=budget.pk)


class FutureBudgetBulkProposalSaveView(LoginRequiredMixin, View):
    """Save outflow and inflow proposals for multiple Draft lines in one submission."""

    @db_transaction.atomic
    def post(self, request, pk):
        profile = getattr(request.user, 'profile', None)
        if not profile or profile.role not in MANAGEMENT_ROLES:
            raise PermissionDenied('Only Management or Administrator may update future-budget proposals.')
        budget = get_object_or_404(FutureBudget, pk=pk, account=request.account)
        if budget.status not in (FutureBudget.Status.DRAFT, FutureBudget.Status.PROPOSED, FutureBudget.Status.APPROVED):
            raise PermissionDenied('Proposals can only be updated while the budget is Draft, Proposed, or Approved.')

        line_ids = request.POST.getlist('line_ids')
        updated_count = 0
        error_count = 0
        for lid in line_ids:
            try:
                line = budget.lines.select_related('account_head').get(pk=lid)
            except FutureBudgetLine.DoesNotExist:
                continue

            has_out_input = f'proposed_{lid}' in request.POST
            has_in_input = f'inflow_proposed_{lid}' in request.POST
            raw_proposed = request.POST.get(f'proposed_{lid}', '').strip()
            raw_inflow = request.POST.get(f'inflow_proposed_{lid}', '').strip()
            justification = request.POST.get(f'justification_{lid}', '').strip()

            try:
                amount = Decimal(raw_proposed) if (has_out_input and raw_proposed) else None
                inflow_amount = Decimal(raw_inflow) if (has_in_input and raw_inflow) else None
                if amount is not None and amount < 0:
                    raise ValueError
                if inflow_amount is not None and inflow_amount < 0:
                    raise ValueError
            except (InvalidOperation, TypeError, ValueError):
                error_count += 1
                continue

            changed = False
            try:
                if has_out_input:
                    if raw_proposed:
                        if not _is_outflow_side(line):
                            raise ValidationError('This Future Budget line does not support outflow proposals.')
                        FutureBudgetWorkflowService.propose(
                            line, amount, request.user,
                            justification=justification,
                        )
                        changed = True
                    elif _is_outflow_side(line) and line.user_proposed is not None:
                        FutureBudgetWorkflowService.reject_proposal(
                            line, request.user, reason='Management outflow proposal cleared.'
                        )
                        changed = True

                if has_in_input:
                    if raw_inflow:
                        if not _is_inflow_side(line):
                            raise ValidationError('This Future Budget line does not support inflow proposals.')
                        FutureBudgetWorkflowService.propose_inflow(
                            line, inflow_amount, request.user,
                            justification=justification,
                        )
                        changed = True
                    elif _is_inflow_side(line) and get_user_proposed_inflow(line) is not None:
                        FutureBudgetWorkflowService.reject_inflow_proposal(
                            line, request.user, reason='Management inflow proposal cleared.'
                        )
                        changed = True
            except ValidationError:
                error_count += 1
                continue

            if changed:
                updated_count += 1

        if budget.status == FutureBudget.Status.APPROVED and updated_count > 0:
            from .future_budget_publication import FutureBudgetPublicationService
            try:
                FutureBudgetPublicationService.publish(budget, request.user, overwrite_existing=True)
            except Exception:
                pass

        if updated_count > 0:
            messages.success(request, f'Saved management budget proposals for {updated_count} line(s).')
        if error_count > 0:
            messages.warning(request, f'{error_count} row(s) had invalid or unsupported amounts and were skipped.')
        return redirect('core:future_budget_review', pk=budget.pk)
