from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.forms import modelformset_factory
from django.forms.utils import ErrorList
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from core.historical_budget_allocation_models import HistoricalBudgetAllocation
from core.models import BudgetLine, UserProfile


HistoricalAllocationFormSet = modelformset_factory(
    HistoricalBudgetAllocation,
    fields=('unit', 'internal_section', 'allocated_amount', 'remarks'),
    extra=1,
    can_delete=True,
)


class HistoricalBudgetAllocationView(LoginRequiredMixin, View):
    """Management UI for explicit organisational attribution of an existing budget line."""
    template_name = 'finance/historical_budget_allocation.html'

    def dispatch(self, request, *args, **kwargs):
        profile = getattr(request.user, 'profile', None)
        if not profile or profile.role not in (UserProfile.Role.ADMINISTRATOR, UserProfile.Role.MANAGEMENT):
            raise PermissionDenied('Only Management or Administrator may manage historical budget allocations.')
        return super().dispatch(request, *args, **kwargs)

    def get_line(self, pk):
        return get_object_or_404(
            BudgetLine.objects.select_related(
                'budget', 'budget__account', 'budget__financial_year',
                'account_head', 'unit', 'budget_type'
            ),
            pk=pk,
        )

    def get(self, request, pk):
        line = self.get_line(pk)
        formset = HistoricalAllocationFormSet(
            queryset=line.historical_allocations.select_related('unit', 'internal_section')
        )
        return render(request, self.template_name, self.context(line, formset))

    def post(self, request, pk):
        line = self.get_line(pk)
        formset = HistoricalAllocationFormSet(
            request.POST, queryset=line.historical_allocations.all()
        )
        if not formset.is_valid():
            return render(request, self.template_name, self.context(line, formset))

        try:
            with transaction.atomic():
                instances = formset.save(commit=False)
                for deleted in formset.deleted_objects:
                    deleted.delete()
                for allocation in instances:
                    allocation.budget_line = line
                    allocation.save()

                total = sum((a.allocated_amount for a in line.historical_allocations.all()), 0)
                if total != line.amount:
                    raise ValidationError(
                        f'Allocation must reconcile exactly to Rs {line.amount:,.2f}. '
                        f'Current allocation total is Rs {total:,.2f}.'
                    )

            messages.success(request, 'Historical organisational allocation saved and reconciled.')
            return redirect('core:historical_budget_allocation', pk=line.pk)
        except ValidationError as exc:
            formset._non_form_errors = ErrorList([str(exc)])
            return render(request, self.template_name, self.context(line, formset))

    @staticmethod
    def context(line, formset):
        allocated = sum((a.allocated_amount for a in line.historical_allocations.all()), 0)
        return {
            'line': line,
            'formset': formset,
            'target_amount': line.amount,
            'allocated_amount': allocated,
            'difference': line.amount - allocated,
            'is_reconciled': line.amount == allocated,
        }
