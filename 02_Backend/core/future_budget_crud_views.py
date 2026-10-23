from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .future_budget_services import build_future_budget_lines, get_future_budget_summary, get_salaries_baseline
from .models import (
    AccountHead,
    FinancialYear,
    FutureBudget,
    FutureBudgetKnownChange,
    FutureBudgetLine,
    FutureBudgetPersonnel,
)


class FutureBudgetBuildView(LoginRequiredMixin, View):
    def post(self, request, pk):
        fb = get_object_or_404(FutureBudget, pk=pk, account=request.account)
        if fb.status in (FutureBudget.Status.DRAFT, FutureBudget.Status.PROPOSED):
            build_future_budget_lines(fb)
            messages.success(request, 'Future budget lines built from historical data.')
        else:
            messages.error(request, 'Only a Draft or Proposed future budget can be rebuilt.')
        return redirect('core:future_budget_detail', pk=fb.pk)


class FutureBudgetListView(LoginRequiredMixin, ListView):
    model = FutureBudget
    template_name = 'future_budget/list.html'
    context_object_name = 'future_budgets'

    def get_queryset(self):
        return FutureBudget.objects.filter(account=self.request.account)


class FutureBudgetCreateView(LoginRequiredMixin, CreateView):
    model = FutureBudget
    fields = [
        'source_fy', 'target_fy', 'personnel_revision_pct',
        'routine_adjustment_pct', 'reference', 'remarks',
    ]
    template_name = 'future_budget/form.html'
    success_url = reverse_lazy('core:future_budget_list')

    def get_initial(self):
        initial = super().get_initial()
        for field, code in (('source_fy', '2025-26'), ('target_fy', '2026-27')):
            try:
                initial[field] = FinancialYear.objects.get(code=code)
            except FinancialYear.DoesNotExist:
                pass
        return initial

    def form_valid(self, form):
        from django.db import IntegrityError
        form.instance.account = self.request.account
        form.instance.created_by = self.request.user
        try:
            return super().form_valid(form)
        except IntegrityError:
            source = form.cleaned_data.get('source_fy')
            target = form.cleaned_data.get('target_fy')
            form.add_error(
                None,
                f"A future budget for {self.request.account.code} from "
                f"{source} → {target} already exists. "
                f"Please choose a different source or target financial year, or edit the existing record."
            )
            return self.form_invalid(form)


class FutureBudgetDetailView(LoginRequiredMixin, DetailView):
    model = FutureBudget
    template_name = 'future_budget/detail.html'
    context_object_name = 'future_budget'

    def get_queryset(self):
        return FutureBudget.objects.filter(account=self.request.account)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        fb = self.object
        ctx['lines'] = fb.lines.all()
        ctx['known_changes'] = fb.known_changes.all()
        ctx['personnel_lines'] = fb.personnel_lines.all()
        ctx['summary'] = get_future_budget_summary(fb)
        return ctx


class FutureBudgetLineUpdateView(LoginRequiredMixin, UpdateView):
    model = FutureBudgetLine
    fields = ['user_proposed', 'justification', 'remarks']
    template_name = 'future_budget/line_edit.html'

    def get_queryset(self):
        return FutureBudgetLine.objects.filter(
            future_budget__account=self.request.account,
        ).select_related('future_budget', 'future_budget__account', 'future_budget__source_fy', 'future_budget__target_fy', 'account_head', 'major_head', 'sub_head')

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['user_proposed'].label = 'Management Proposed Amount'
        form.fields['user_proposed'].widget.attrs.update({
            'class': 'w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-300 font-mono font-bold text-lg text-slate-800 focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 bg-white shadow-xs',
            'placeholder': '0.00',
            'step': '0.01',
        })
        form.fields['justification'].label = 'Operational Justification / Rationale'
        form.fields['justification'].widget.attrs.update({
            'class': 'w-full px-4 py-2.5 rounded-xl border border-slate-300 text-sm text-slate-800 placeholder-slate-400 focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 bg-white shadow-xs',
            'rows': '3',
            'placeholder': 'Provide justification for this proposed allocation (e.g. routine increase, new policy, cost increase)...',
        })
        form.fields['remarks'].label = 'Internal Remarks / Audit Notes'
        form.fields['remarks'].widget.attrs.update({
            'class': 'w-full px-4 py-2.5 rounded-xl border border-slate-300 text-sm text-slate-800 placeholder-slate-400 focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 bg-white shadow-xs',
            'rows': '2',
            'placeholder': 'Optional internal remarks or reference note...',
        })
        return form

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        line = self.object
        fb = line.future_budget
        ctx['future_budget'] = fb
        ctx['account_head'] = line.account_head
        ctx['is_approved'] = fb.status == FutureBudget.Status.APPROVED
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        fb = self.object.future_budget
        if fb.status == FutureBudget.Status.APPROVED:
            from .future_budget_publication import FutureBudgetPublicationService
            try:
                FutureBudgetPublicationService.publish(fb, self.request.user, overwrite_existing=True)
            except Exception:
                pass
        return response

    def get_success_url(self):
        return reverse_lazy('core:future_budget_detail', args=[self.object.future_budget.pk])


class KnownChangeCreateView(LoginRequiredMixin, CreateView):
    model = FutureBudgetKnownChange
    fields = ['description', 'change_type', 'account_head', 'amount', 'justification', 'reference']
    template_name = 'future_budget/known_changes.html'

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        fb = get_object_or_404(
            FutureBudget,
            pk=self.kwargs['budget_id'],
            account=self.request.account,
        )
        form.fields['account_head'].queryset = AccountHead.objects.filter(
            account=fb.account,
            is_active=True,
        ).order_by('code', 'name')
        return form

    def form_valid(self, form):
        fb = get_object_or_404(FutureBudget, pk=self.kwargs['budget_id'], account=self.request.account)
        if fb.status != FutureBudget.Status.DRAFT:
            raise PermissionDenied('Known changes can only be added while the future budget is Draft.')
        form.instance.future_budget = fb
        form.instance.created_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('core:future_budget_detail', args=[self.kwargs['budget_id']])


class PersonnelPlanView(LoginRequiredMixin, View):
    def get(self, request, pk):
        fb = get_object_or_404(FutureBudget, pk=pk, account=request.account)
        lines = list(fb.personnel_lines.all())
        if not lines:
            salaries = get_salaries_baseline(fb.account, fb.source_fy)
            lines = [FutureBudgetPersonnel.objects.create(
                future_budget=fb,
                category_label='Existing Personnel',
                current_annual_cost=salaries,
                revision_pct=fb.personnel_revision_pct,
            )]
            messages.success(request, 'Personnel baseline created from the source financial year.')
        return render(request, 'future_budget/personnel.html', {'future_budget': fb, 'lines': lines})

    def post(self, request, pk):
        fb = get_object_or_404(FutureBudget, pk=pk, account=request.account)
        if fb.status != FutureBudget.Status.DRAFT:
            messages.error(request, 'Personnel planning can only be changed while the future budget is Draft.')
            return redirect('core:future_budget_detail', pk=fb.pk)
        return self.get(request, pk)


class FutureBudgetUpdateView(LoginRequiredMixin, UpdateView):
    """Edit basic fields (source/target FY, adjustment %, reference) of a DRAFT Future Budget."""
    model = FutureBudget
    fields = ['source_fy', 'target_fy', 'personnel_revision_pct', 'routine_adjustment_pct', 'reference', 'remarks']
    template_name = 'future_budget/form.html'

    def get_object(self, queryset=None):
        fb = get_object_or_404(FutureBudget, pk=self.kwargs['pk'], account=self.request.account)
        if fb.status not in (FutureBudget.Status.DRAFT, FutureBudget.Status.PROPOSED):
            raise PermissionDenied('Only DRAFT or PROPOSED future budgets can be edited.')
        return fb

    def get_success_url(self):
        return reverse_lazy('core:future_budget_detail', args=[self.object.pk])


class FutureBudgetDeleteView(LoginRequiredMixin, View):
    """Individual Future Budget delete (POST). Only DRAFT budgets can be deleted."""
    def post(self, request, pk):
        fb = get_object_or_404(FutureBudget, pk=pk, account=request.account)
        if fb.status != FutureBudget.Status.DRAFT:
            messages.error(request, 'Only DRAFT future budgets can be deleted.')
            return redirect('core:future_budget_list')
        label = f"{fb.account.code} {fb.source_fy.code}→{fb.target_fy.code}"
        fb.delete()
        messages.success(request, f'Future budget "{label}" deleted successfully.')
        return redirect('core:future_budget_list')
