from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from .future_budget_services import build_future_budget_lines, get_future_budget_summary
from .models import (
    FutureBudget, FutureBudgetLine, AccountHead, Unit, InternalSection,
)
from .future_budget_management_models import FutureBudgetManagementInput


class FutureBudgetReviewView(LoginRequiredMixin, View):
    template_name = 'future_budget/review.html'

    def _get_budget(self, request, pk):
        return get_object_or_404(FutureBudget, pk=pk, account=request.account)

    def get(self, request, pk):
        from decimal import Decimal
        from .future_budget_inflow_proposal import get_user_proposed_inflow
        fb = self._get_budget(request, pk)

        active_master_head_ids = set(
            AccountHead.objects.filter(account=fb.account, is_active=True).values_list('id', flat=True)
        )
        existing_line_head_ids = set(fb.lines.values_list('account_head_id', flat=True))
        if active_master_head_ids - existing_line_head_ids:
            build_future_budget_lines(fb, allow_approved=True)

        lines = list(
            fb.lines.select_related('account_head', 'major_head', 'sub_head')
            .order_by(
                'major_head__display_order',
                'major_head__code',
                'account_head__display_order',
                'account_head__name',
                'pk',
            )
            .all()
        )
        outflow_lines = []
        inflow_lines = []

        for line in lines:
            head = line.account_head
            bd = line.suggestion_breakdown or {}
            line.inflow_prev_budget = Decimal(str(bd.get('previous_inflow_budget') or '0.00'))
            line.inflow_prev_actual = Decimal(str(bd.get('previous_inflow_actual') or '0.00'))
            line.inflow_suggested = Decimal(str(bd.get('suggested_inflow') or '0.00'))
            line.proposed_inflow = get_user_proposed_inflow(line)
            if line.proposed_inflow is None and line.approved_inflow_amount is not None:
                line.proposed_inflow = line.approved_inflow_amount

            if head is None:
                # Sub-Fund based allocation line
                is_outflow = (
                    line.previous_actual > Decimal('0.00') or
                    line.previous_budget > Decimal('0.00') or
                    line.system_suggested > Decimal('0.00') or
                    (line.user_proposed is not None and line.user_proposed > Decimal('0.00')) or
                    (line.approved_amount is not None and line.approved_amount > Decimal('0.00'))
                )
                is_inflow = (
                    line.inflow_prev_actual > Decimal('0.00') or
                    line.inflow_prev_budget > Decimal('0.00') or
                    line.inflow_suggested > Decimal('0.00') or
                    (line.proposed_inflow is not None and line.proposed_inflow > Decimal('0.00')) or
                    (line.approved_inflow_amount is not None and line.approved_inflow_amount > Decimal('0.00'))
                )
                if not is_outflow and not is_inflow:
                    is_outflow = True
            else:
                is_outflow = (head.head_type in ('OUTFLOW', 'BOTH')) and (
                    line.previous_actual > Decimal('0.00') or
                    line.previous_budget > Decimal('0.00') or
                    line.system_suggested > Decimal('0.00') or
                    (line.user_proposed is not None and line.user_proposed > Decimal('0.00')) or
                    (line.approved_amount is not None and line.approved_amount > Decimal('0.00'))
                )
                is_inflow = (head.head_type == AccountHead.HeadType.INFLOW) or (
                    head.head_type == AccountHead.HeadType.BOTH and (
                        line.inflow_prev_actual > Decimal('0.00') or
                        line.inflow_prev_budget > Decimal('0.00') or
                        (line.proposed_inflow is not None and line.proposed_inflow > Decimal('0.00')) or
                        (line.approved_inflow_amount is not None and line.approved_inflow_amount > Decimal('0.00'))
                    )
                )

            if is_outflow:
                outflow_lines.append(line)
            if is_inflow:
                inflow_lines.append(line)

        inflow_lines.sort(key=lambda l: (
            0 if (l.account_head and l.account_head.head_type == AccountHead.HeadType.INFLOW) else 1,
            l.account_head.display_order if l.account_head else (l.major_head.display_order if l.major_head else 0),
            l.account_head.name if l.account_head else (l.major_head.name if l.major_head else ''),
        ))

        inputs = FutureBudgetManagementInput.objects.filter(
            future_budget=fb
        ).select_related('account_head').prefetch_related('units', 'internal_sections')
        context = {
            'future_budget': fb,
            'lines': lines,
            'outflow_lines': outflow_lines,
            'inflow_lines': inflow_lines,
            'management_inputs': inputs,
            'summary': get_future_budget_summary(fb),
            'account_heads': AccountHead.objects.filter(account=fb.account, is_active=True),
            'units': Unit.objects.filter(is_active=True),
            'internal_sections': InternalSection.objects.filter(is_active=True),
        }
        return render(request, self.template_name, context)


class FutureBudgetReviewBuildView(LoginRequiredMixin, View):
    def post(self, request, pk):
        fb = get_object_or_404(FutureBudget, pk=pk, account=request.account)
        if fb.status not in (FutureBudget.Status.DRAFT, FutureBudget.Status.PROPOSED):
            messages.error(request, 'Only a Draft or Proposed future budget can be recalculated.')
            return redirect('core:future_budget_review', pk=pk)
        build_future_budget_lines(fb)
        messages.success(request, 'System suggestions recalculated from the transaction SSOT and active management inputs.')
        return redirect('core:future_budget_review', pk=pk)


class FutureBudgetManagementInputCreateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        fb = get_object_or_404(FutureBudget, pk=pk, account=request.account)
        if fb.status not in (FutureBudget.Status.DRAFT, FutureBudget.Status.PROPOSED):
            raise PermissionDenied('Management inputs can only be changed while the future budget is Draft or Proposed.')

        account_head_id = request.POST.get('account_head')
        input_type = request.POST.get('input_type')
        description = request.POST.get('description', '').strip()
        amount = request.POST.get('amount')
        reference = request.POST.get('reference', '').strip()
        justification = request.POST.get('justification', '').strip()

        try:
            head = AccountHead.objects.get(pk=account_head_id, account=fb.account, is_active=True)
            if input_type not in dict(FutureBudgetManagementInput.InputType.choices):
                raise ValueError('Invalid input type')
            from decimal import Decimal
            amount_value = Decimal(amount)
            if amount_value <= 0:
                raise ValueError('Amount must be greater than zero')
        except (AccountHead.DoesNotExist, ValueError, TypeError, ArithmeticError):
            messages.error(request, 'Please provide a valid Account Head, input type and positive amount.')
            return redirect('core:future_budget_review', pk=pk)

        row = FutureBudgetManagementInput.objects.create(
            future_budget=fb,
            account_head=head,
            input_type=input_type,
            description=description,
            amount=amount_value,
            reference=reference,
            justification=justification,
            status=FutureBudgetManagementInput.Status.ACTIVE,
            created_by=request.user,
        )

        unit_ids = request.POST.getlist('units')
        section_ids = request.POST.getlist('internal_sections')
        row.units.set(Unit.objects.filter(pk__in=unit_ids, is_active=True))
        row.internal_sections.set(InternalSection.objects.filter(pk__in=section_ids, is_active=True))
        messages.success(request, 'Management input added as Active. Recalculate the system suggestion to incorporate it.')
        return redirect('core:future_budget_review', pk=pk)
