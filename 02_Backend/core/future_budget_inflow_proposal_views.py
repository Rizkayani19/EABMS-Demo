from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from .budget_inflow_models import BudgetInflowLine
from .future_budget_inflow_proposal import get_user_proposed_inflow
from .future_budget_management_models import FutureBudgetDecisionHistory
from .future_budget_workflow import FutureBudgetWorkflowService
from .models import AccountHead, FutureBudget, FutureBudgetLine, Transaction, UserProfile


MANAGEMENT_ROLES = (UserProfile.Role.ADMINISTRATOR, UserProfile.Role.MANAGEMENT)


class FutureBudgetInflowProposalView(LoginRequiredMixin, View):
    """Dedicated Draft-only screen for management inflow proposals."""
    template_name = 'future_budget/inflow_proposal.html'

    def get_budget(self, request, pk):
        return get_object_or_404(FutureBudget, pk=pk, account=request.account)

    def get(self, request, pk):
        budget = self.get_budget(request, pk)
        source_fy = budget.source_fy
        inflow_heads = AccountHead.objects.filter(
            account=budget.account,
            is_active=True,
        ).filter(
            Q(head_type=AccountHead.HeadType.INFLOW) | Q(head_type=AccountHead.HeadType.BOTH)
        ).order_by('display_order', 'name')

        actuals = {
            r['account_head_id']: (r['total'] or Decimal('0.00'))
            for r in Transaction.objects.filter(
                account=budget.account,
                financial_year=source_fy,
                direction=Transaction.Direction.INFLOW,
                status=Transaction.Status.ACTIVE,
            ).values('account_head_id').annotate(total=Sum('amount'))
        }
        budgeted = {
            r['account_head_id']: (r['total'] or Decimal('0.00'))
            for r in BudgetInflowLine.objects.filter(
                budget__account=budget.account,
                budget__financial_year=source_fy,
                account_head__in=inflow_heads,
            ).values('account_head_id').annotate(total=Sum('amount'))
        }
        line_map = {
            line.account_head_id: line
            for line in FutureBudgetLine.objects.filter(
                future_budget=budget,
                account_head__in=inflow_heads,
            )
        }
        rows = []
        for head in inflow_heads:
            line = line_map.get(head.id)
            rows.append({
                'head': head,
                'line': line,
                'previous_budget': budgeted.get(head.id, Decimal('0.00')),
                'previous_actual': actuals.get(head.id, Decimal('0.00')),
                'user_proposed_inflow': get_user_proposed_inflow(line) if line else None,
                'approved_inflow': line.approved_inflow_amount if line else None,
            })

        proposed_total = sum(
            (row['user_proposed_inflow'] or Decimal('0.00')) for row in rows
        )
        approved_total = sum(
            (row['approved_inflow'] or Decimal('0.00')) for row in rows
        )
        audit = FutureBudgetDecisionHistory.objects.filter(
            future_budget_line__future_budget=budget,
        ).select_related(
            'future_budget_line__account_head', 'actor'
        )[:25]
        return render(request, self.template_name, {
            'future_budget': budget,
            'rows': rows,
            'proposed_inflow_total': proposed_total,
            'approved_inflow_total': approved_total,
            'decision_history': audit,
        })

    def post(self, request, pk):
        profile = getattr(request.user, 'profile', None)
        if not profile or profile.role not in MANAGEMENT_ROLES:
            raise PermissionDenied('Only Management or Administrator may enter inflow proposals.')
        budget = self.get_budget(request, pk)
        if budget.status not in (FutureBudget.Status.DRAFT, FutureBudget.Status.PROPOSED):
            raise PermissionDenied('Inflow proposals can only be changed while the future budget is Draft or Proposed.')

        line_ids = request.POST.getlist('line_ids')
        updated = 0
        errors = 0
        for lid in line_ids:
            try:
                line = FutureBudgetLine.objects.select_related('account_head').get(
                    pk=lid, future_budget=budget,
                )
            except FutureBudgetLine.DoesNotExist:
                continue
            if line.account_head.head_type not in ('INFLOW', 'BOTH'):
                continue
            raw = request.POST.get(f'inflow_proposed_{lid}', '').strip()
            try:
                amount = Decimal(raw) if raw else None
                if amount is not None and amount < 0:
                    raise ValueError
            except (InvalidOperation, TypeError, ValueError):
                errors += 1
                continue

            try:
                previous = get_user_proposed_inflow(line)
                if amount is None:
                    if previous is not None:
                        FutureBudgetWorkflowService.reject_inflow_proposal(
                            line, request.user, reason='Management inflow proposal cleared.'
                        )
                    else:
                        continue
                else:
                    FutureBudgetWorkflowService.propose_inflow(
                        line,
                        amount,
                        request.user,
                        justification=(request.POST.get(f'justification_{lid}', '') or '').strip(),
                        remarks=(request.POST.get(f'remarks_{lid}', '') or '').strip(),
                    )
                updated += 1
            except ValidationError as exc:
                errors += 1
                messages.error(request, str(exc))

        if updated:
            messages.success(request, f'Saved inflow management proposals for {updated} account head(s).')
        if errors:
            messages.warning(request, f'{errors} inflow row(s) could not be saved.')
        return redirect('core:future_budget_inflow_proposal', pk=budget.pk)
