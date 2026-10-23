from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .models import Budget, BudgetLine, BudgetRevision, AccountHead, MajorHead, BudgetType, Transaction, Unit
from .budget_inflow_models import BudgetInflowLine
from .views import BaseFinanceView, FinancialEditMixin


class BudgetListView(BaseFinanceView, ListView):
    model = Budget
    template_name = 'finance/budget_list.html'
    context_object_name = 'budgets'

    def get_queryset(self):
        return Budget.objects.filter(account=self.request.account, financial_year=self.request.fy).prefetch_related('lines', 'inflow_lines')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from .models import FutureBudget
        from .future_budget_services import get_future_budget_summary
        from .future_budget_inflow_proposal import get_user_proposed_inflow
        from django.db.models import Q

        future_budgets = list(
            FutureBudget.objects.filter(
                account=self.request.account
            ).filter(
                Q(target_fy=self.request.fy) | Q(source_fy=self.request.fy)
            ).select_related('target_fy', 'source_fy', 'created_by').prefetch_related('lines__account_head').order_by('-created_at')
        )
        for fb in future_budgets:
            fb.summary = get_future_budget_summary(fb)
            inflow_prop = Decimal('0.00')
            inflow_appr = Decimal('0.00')
            for l in fb.lines.all():
                p_in = get_user_proposed_inflow(l)
                if p_in is not None:
                    inflow_prop += p_in
                if l.approved_inflow_amount is not None:
                    inflow_appr += l.approved_inflow_amount
            fb.inflow_proposed_total = inflow_prop
            fb.inflow_approved_total = inflow_appr
            fb.net_proposed_diff = inflow_prop - (fb.summary.get('user_proposed_total') or Decimal('0.00'))

        ctx['future_budgets'] = future_budgets
        return ctx


class BudgetCreateView(FinancialEditMixin, BaseFinanceView, CreateView):
    model = Budget
    fields = ['status', 'reference', 'remarks']
    template_name = 'finance/budget_form.html'
    success_url = reverse_lazy('core:budget_list')

    def form_valid(self, form):
        form.instance.account = self.request.account
        form.instance.financial_year = self.request.fy
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class BudgetUpdateView(FinancialEditMixin, BaseFinanceView, UpdateView):
    model = Budget
    fields = ['status', 'reference', 'remarks']
    template_name = 'finance/budget_form.html'
    success_url = reverse_lazy('core:budget_list')

    def get_object(self, queryset=None):
        return get_object_or_404(Budget, pk=self.kwargs['pk'], account=self.request.account, financial_year=self.request.fy)

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        return super().form_valid(form)


class BudgetDetailView(BaseFinanceView, DetailView):
    model = Budget
    template_name = 'finance/budget_detail.html'
    context_object_name = 'budget'

    def get_object(self, queryset=None):
        return get_object_or_404(Budget.objects.prefetch_related('lines__account_head', 'lines__budget_type', 'lines__unit', 'inflow_lines__account_head', 'inflow_lines__budget_type', 'inflow_lines__unit'), pk=self.kwargs['pk'], account=self.request.account, financial_year=self.request.fy)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['inflow_total'] = self.object.inflow_lines.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
        ctx['outflow_total'] = self.object.lines.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
        ctx['budget_difference'] = ctx['inflow_total'] - ctx['outflow_total']
        return ctx


class BudgetLineAdderForm(forms.Form):
    major_head = forms.ModelChoiceField(queryset=MajorHead.objects.none(), required=False, label='Sub-Fund')
    account_head = forms.ModelChoiceField(queryset=AccountHead.objects.none(), required=False, label='Account Head')
    unit = forms.ModelChoiceField(queryset=Unit.objects.none(), required=False, label='Unit / Organisation')
    budget_type = forms.ModelChoiceField(queryset=BudgetType.objects.none(), label='Budget Type')
    amount = forms.DecimalField(required=False, min_value=Decimal('0.00'), decimal_places=2, max_digits=18, label='Outflow Budget (Rs)')
    inflow_amount = forms.DecimalField(required=False, min_value=Decimal('0.00'), decimal_places=2, max_digits=18, label='Inflow Budget (Rs)')
    remarks = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 3}), label='Remarks')

    def __init__(self, *args, account=None, is_sub_fund_basis=False, **kwargs):
        kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        self.is_sub_fund_basis = is_sub_fund_basis
        self.fields['major_head'].queryset = MajorHead.objects.filter(account=account, is_active=True).order_by('display_order', 'name')
        self.fields['account_head'].queryset = AccountHead.objects.filter(account=account, is_active=True).order_by('display_order', 'name')
        self.fields['unit'].queryset = Unit.objects.filter(is_active=True).order_by('display_order', 'name')
        self.fields['budget_type'].queryset = BudgetType.objects.filter(is_active=True).order_by('display_order', 'name')
        if not is_sub_fund_basis:
            self.fields['major_head'].widget = forms.HiddenInput()

    def clean(self):
        cleaned = super().clean()
        head = cleaned.get('account_head')
        major_head = cleaned.get('major_head')
        outflow = cleaned.get('amount') or Decimal('0.00')
        inflow = cleaned.get('inflow_amount') or Decimal('0.00')
        if not head and not major_head:
            raise forms.ValidationError('Either an Account Head or a Sub-Fund must be selected.')
        if head:
            if head.head_type == AccountHead.HeadType.OUTFLOW and outflow <= 0:
                self.add_error('amount', 'Enter an Outflow Budget amount for an Outflow Account Head.')
            if head.head_type == AccountHead.HeadType.INFLOW and inflow <= 0:
                self.add_error('inflow_amount', 'Enter an Inflow Budget amount for an Inflow Account Head.')
            if head.head_type == AccountHead.HeadType.BOTH and outflow <= 0 and inflow <= 0:
                raise forms.ValidationError('For a BOTH Account Head, enter an Outflow amount, an Inflow amount, or both.')
        elif major_head:
            if outflow <= 0 and inflow <= 0:
                raise forms.ValidationError('Enter an Outflow amount, an Inflow amount, or both for the Sub-Fund.')
        return cleaned


class BudgetLineCreateView(FinancialEditMixin, BaseFinanceView, CreateView):
    model = BudgetLine
    form_class = BudgetLineAdderForm
    template_name = 'finance/budgetline_form.html'

    def _get_budget(self):
        return get_object_or_404(Budget, pk=self.kwargs['budget_id'], account=self.request.account, financial_year=self.request.fy)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.pop('instance', None)
        budget = self._get_budget()
        kwargs['account'] = self.request.account
        kwargs['is_sub_fund_basis'] = (budget.budget_allocation_basis == 'SUB_FUND')
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        budget = self._get_budget()
        ctx['budget'] = budget
        rows = Transaction.objects.filter(account=self.request.account, financial_year=self.request.fy, status=Transaction.Status.ACTIVE).values('account_head_id', 'direction').annotate(total=Sum('amount'))
        metrics = {}
        for row in rows:
            metrics.setdefault(str(row['account_head_id']), {'outflow': '0.00', 'inflow': '0.00'})
            metrics[str(row['account_head_id'])]['outflow' if row['direction'] == Transaction.Direction.OUTFLOW else 'inflow'] = str(row['total'] or Decimal('0.00'))
        ctx['head_metrics'] = metrics
        ctx['account_heads_json'] = {str(h.pk): h.head_type for h in AccountHead.objects.filter(account=self.request.account, is_active=True)}
        return ctx

    def form_valid(self, form):
        budget = self._get_budget()
        head = form.cleaned_data.get('account_head')
        major_head = form.cleaned_data.get('major_head')
        unit = form.cleaned_data.get('unit')
        budget_type = form.cleaned_data['budget_type']
        outflow = form.cleaned_data.get('amount') or Decimal('0.00')
        inflow = form.cleaned_data.get('inflow_amount') or Decimal('0.00')
        remarks = form.cleaned_data.get('remarks', '')
        if head:
            if outflow > 0:
                BudgetLine.objects.create(budget=budget, account_head=head, major_head=head.major_head, sub_head=head.sub_head, unit=unit, budget_type=budget_type, amount=outflow, remarks=remarks)
            if inflow > 0:
                BudgetInflowLine.objects.create(budget=budget, account_head=head, unit=unit, budget_type=budget_type, amount=inflow, remarks=remarks)
            messages.success(self.request, f'Budget planning saved for {head.name}.')
        elif major_head:
            if outflow > 0:
                BudgetLine.objects.create(budget=budget, account_head=None, major_head=major_head, sub_head=None, unit=unit, budget_type=budget_type, amount=outflow, remarks=remarks)
            if inflow > 0:
                BudgetInflowLine.objects.create(budget=budget, account_head=None, major_head=major_head, unit=unit, budget_type=budget_type, amount=inflow, remarks=remarks)
            messages.success(self.request, f'Budget planning saved for {major_head.name}.')
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse_lazy('core:budget_detail', args=[self._get_budget().pk])


class BudgetRevisionCreateView(FinancialEditMixin, BaseFinanceView, CreateView):
    model = BudgetRevision
    fields = ['revised_amount', 'reason', 'reference']
    template_name = 'finance/budgetrevision_form.html'

    def _get_line(self):
        return get_object_or_404(BudgetLine.objects.select_related('budget', 'account_head'), pk=self.kwargs['line_id'], budget__account=self.request.account, budget__financial_year=self.request.fy)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        line = self._get_line()
        instance = kwargs.get('instance') or BudgetRevision()
        instance.budget_line = line
        instance.previous_amount = line.amount
        kwargs['instance'] = instance
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        line = self._get_line()
        ctx['line'] = line
        ctx['revisions'] = BudgetRevision.objects.filter(budget_line=line).order_by('-revised_at')[:5]
        return ctx

    def get_success_url(self):
        return reverse_lazy('core:budget_detail', args=[self._get_line().budget.pk])

    def form_valid(self, form):
        line = self._get_line()
        revised_amount = form.cleaned_data['revised_amount']
        form.instance.difference = revised_amount - line.amount
        form.instance.revised_by = self.request.user
        response = super().form_valid(form)
        line.amount = revised_amount
        line.save(update_fields=['amount', 'updated_at'])
        messages.success(self.request, 'Budget line revised successfully.')
        return response


class BudgetDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        budget = get_object_or_404(Budget, pk=pk, account=request.account, financial_year=request.fy)
        if budget.status == 'APPROVED':
            messages.error(request, 'Approved budgets cannot be deleted. Revoke approval first.')
            return redirect('core:budget_list')
        name = f"Budget #{budget.id} ({budget.reference or 'no ref'})"
        budget.delete()
        messages.success(request, f'{name} deleted successfully.')
        return redirect('core:budget_list')
