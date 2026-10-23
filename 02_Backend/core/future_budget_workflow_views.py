from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.views import View

from .models import FutureBudget, UserProfile
from .future_budget_publication import FutureBudgetPublicationService

MANAGEMENT_ROLES = (
    UserProfile.Role.ADMINISTRATOR,
    UserProfile.Role.MANAGEMENT,
)


class FutureBudgetProposeView(LoginRequiredMixin, View):
    def post(self, request, pk):
        profile = getattr(request.user, 'profile', None)
        if not profile or profile.role not in MANAGEMENT_ROLES:
            raise PermissionDenied('Only Management or Administrator may submit a future budget.')
        budget = get_object_or_404(FutureBudget, pk=pk, account=request.account)
        budget.status = FutureBudget.Status.PROPOSED
        budget.save(update_fields=['status', 'updated_at'])
        messages.success(request, 'Future budget submitted for management review.')
        return redirect('core:future_budget_review', pk=budget.pk)


class FutureBudgetRevertDraftView(LoginRequiredMixin, View):
    def post(self, request, pk):
        profile = getattr(request.user, 'profile', None)
        if not profile or profile.role not in MANAGEMENT_ROLES:
            raise PermissionDenied('Only Management or Administrator may revert a future budget.')
        budget = get_object_or_404(FutureBudget, pk=pk, account=request.account)
        budget.status = FutureBudget.Status.DRAFT
        budget.save(update_fields=['status', 'updated_at'])
        messages.success(request, 'Future budget reopened and returned to Draft status for editing.')
        return redirect('core:future_budget_review', pk=budget.pk)


class FutureBudgetApproveView(LoginRequiredMixin, View):
    def post(self, request, pk):
        profile = getattr(request.user, 'profile', None)
        if not profile or profile.role not in MANAGEMENT_ROLES:
            raise PermissionDenied('Only Management or Administrator may approve a future budget.')
        budget = get_object_or_404(FutureBudget, pk=pk, account=request.account)
        if budget.status not in (FutureBudget.Status.PROPOSED, FutureBudget.Status.APPROVED):
            messages.error(request, 'Only a Proposed or Approved future budget can be approved.')
            return redirect('core:future_budget_review', pk=budget.pk)

        try:
            target_budget = FutureBudgetPublicationService.publish(budget, request.user, overwrite_existing=True)
        except ValidationError as exc:
            message = '; '.join(str(error) for error in exc.messages)
            messages.error(request, f'Future budget approval failed: {message}')
            return redirect('core:future_budget_review', pk=budget.pk)

        messages.success(
            request,
            f'Future budget approved and published as Budget #{target_budget.pk} for {budget.target_fy.code}.'
        )
        return redirect('core:budget_detail', pk=target_budget.pk)
