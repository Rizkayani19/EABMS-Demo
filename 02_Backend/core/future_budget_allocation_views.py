from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.forms import modelformset_factory
from django.forms.utils import ErrorList
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from core.future_budget_allocation_models import FutureBudgetAllocation
from core.future_budget_allocation_services import allocation_reconciliation, get_parent_target
from core.models import FutureBudgetLine, UserProfile


AllocationFormSet = modelformset_factory(
    FutureBudgetAllocation,
    fields=('unit', 'internal_section', 'allocated_amount', 'justification', 'remarks'),
    extra=1,
    can_delete=True,
)


class FutureBudgetAllocationView(LoginRequiredMixin, View):
    template_name = 'finance/future_budget_allocation.html'

    def dispatch(self, request, *args, **kwargs):
        profile = getattr(request.user, 'profile', None)
        if not profile or profile.role not in (UserProfile.Role.ADMINISTRATOR, UserProfile.Role.MANAGEMENT):
            raise PermissionDenied('Only Management or Administrator may manage future budget allocations.')
        return super().dispatch(request, *args, **kwargs)

    def get_line(self, pk):
        return get_object_or_404(
            FutureBudgetLine.objects.select_related('future_budget', 'account_head'), pk=pk
        )

    def get(self, request, pk):
        line = self.get_line(pk)
        formset = AllocationFormSet(queryset=line.allocations.select_related('unit', 'internal_section'))
        return render(request, self.template_name, self.context(line, formset))

    def post(self, request, pk):
        line = self.get_line(pk)
        formset = AllocationFormSet(request.POST, queryset=line.allocations.all())
        if not formset.is_valid():
            return render(request, self.template_name, self.context(line, formset))

        try:
            with transaction.atomic():
                instances = formset.save(commit=False)
                for deleted in formset.deleted_objects:
                    deleted.delete()
                for allocation in instances:
                    allocation.future_budget_line = line
                    allocation.updated_by = request.user
                    if not allocation.created_by_id:
                        allocation.created_by = request.user
                    allocation.save()

                reconciliation = allocation_reconciliation(line)
                if not reconciliation['is_reconciled']:
                    raise ValidationError(
                        f"Allocation must reconcile exactly to Rs {reconciliation['target']:,.2f}. "
                        f"Current total is Rs {reconciliation['allocated']:,.2f}."
                    )

            messages.success(request, 'Future budget organisational allocation saved and reconciled.')
            return redirect('core:future_budget_allocation', pk=line.pk)
        except ValidationError as exc:
            formset._non_form_errors = ErrorList([str(exc)])
            return render(request, self.template_name, self.context(line, formset))

    @staticmethod
    def context(line, formset):
        reconciliation = allocation_reconciliation(line)
        return {
            'line': line,
            'future_budget': line.future_budget,
            'formset': formset,
            'target_amount': get_parent_target(line),
            'allocated_amount': reconciliation['allocated'],
            'difference': reconciliation['difference'],
            'is_reconciled': reconciliation['is_reconciled'],
        }
