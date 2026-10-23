from datetime import datetime, date
import json
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView, FormView

from .forms import InflowForm, OutflowForm, ReimbursementForm, InternalTransferForm
from .models import (
    AccountHead, Document, DocumentLink, DocumentType, InflowType, InternalSection,
    MajorHead, OutflowNature, Reimbursement, SubHead, Transaction, Unit, UserProfile,
)
from .services import log_audit_action, get_total_pass_through


def assign_transaction_number(transaction):
    """Assign a collision-resistant operational transaction number on creation."""
    if transaction.transaction_number:
        return
    account_code = getattr(transaction.account, 'code', 'ACC')
    fy_code = getattr(transaction.financial_year, 'code', 'FY')
    compact_fy = fy_code.replace('-', '') if fy_code else 'FY'
    transaction.transaction_number = f"TXN-{account_code}-{compact_fy}-{uuid4().hex[:10].upper()}"


class BaseFinanceView(LoginRequiredMixin):
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['account'] = self.request.account
        ctx['fy'] = self.request.fy
        # Canonical masters used by the transaction attribution controls.
        ctx['transaction_units_master'] = Unit.objects.filter(is_active=True).order_by('display_order', 'name')
        ctx['transaction_sections_master'] = InternalSection.objects.filter(is_active=True).order_by('display_order', 'name')
        return ctx


class FinancialEditMixin:
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        profile = getattr(request.user, 'profile', None)
        if profile and profile.role == UserProfile.Role.MANAGEMENT:
            raise PermissionDenied('Management role cannot edit financial records.')
        return super().dispatch(request, *args, **kwargs)


def handle_document_upload(request, instance, entity_type='TRANSACTION'):
    document_file = request.FILES.get('document')
    if not document_file:
        return
    doc_type, _ = DocumentType.objects.get_or_create(code='GENERAL', defaults={'name': 'General Document'})
    doc = Document.objects.create(document_type=doc_type, file=document_file, file_name=document_file.name, uploaded_by=request.user)
    DocumentLink.objects.create(document=doc, entity_type=entity_type, entity_id=str(instance.id), created_by=request.user)


def load_account_heads(request):
    """Return active Account Heads for the selected Sub Fund (Tier 1)."""
    major_head_id = request.GET.get('major_head') or request.GET.get('source_major_head') or request.GET.get('dest_major_head')
    account = getattr(request, 'account', None)
    qs = AccountHead.objects.filter(is_active=True)
    if account:
        qs = qs.filter(account=account)
    if major_head_id:
        qs = qs.filter(major_head_id=major_head_id)
    direction = (request.GET.get('direction') or '').upper()
    head_type = request.GET.get('head_type')
    if direction == 'INFLOW':
        qs = qs.filter(head_type__in=[AccountHead.HeadType.INFLOW, AccountHead.HeadType.BOTH])
    elif direction == 'OUTFLOW':
        qs = qs.filter(head_type__in=[AccountHead.HeadType.OUTFLOW, AccountHead.HeadType.BOTH])
    elif head_type:
        qs = qs.filter(head_type=head_type)

    account_heads = list(qs.order_by('display_order', 'name'))
    if request.headers.get('HX-Request') or request.GET.get('format') == 'html':
        html = ['<option value="">--------- Select Account Head ---------</option>']
        for ah in account_heads:
            html.append(f'<option value="{ah.id}">{ah.name}</option>')
        return HttpResponse(''.join(html), content_type='text/html')
    return JsonResponse([{'id': ah.id, 'name': ah.name} for ah in account_heads], safe=False)


def load_sub_heads(request):
    """Return active sub-heads for the selected Account Head (Tier 2) or Sub Fund (Tier 1)."""
    account_head_id = request.GET.get('account_head') or request.GET.get('source_account_head') or request.GET.get('dest_account_head')
    major_head_id = request.GET.get('major_head') or request.GET.get('source_major_head') or request.GET.get('dest_major_head')
    account = getattr(request, 'account', None)
    qs = SubHead.objects.filter(is_active=True)
    if account:
        qs = qs.filter(account=account)
    if account_head_id:
        sub_qs = qs.filter(account_head_id=account_head_id)
        if sub_qs.exists():
            qs = sub_qs
        else:
            ah = AccountHead.objects.filter(id=account_head_id).first()
            if ah and ah.major_head_id:
                qs = qs.filter(major_head_id=ah.major_head_id)
            else:
                qs = SubHead.objects.none()
    elif major_head_id:
        qs = qs.filter(major_head_id=major_head_id)
    subheads = list(qs.order_by('display_order', 'name'))
    if request.headers.get('HX-Request') or request.GET.get('format') == 'html':
        html = ['<option value="">--------- (Optional) ---------</option>']
        for sh in subheads:
            html.append(f'<option value="{sh.id}">{sh.name}</option>')
        return HttpResponse(''.join(html), content_type='text/html')
    return JsonResponse([{'id': sh.id, 'name': sh.name} for sh in subheads], safe=False)


def _add_model_validation_errors(form, exc):
    if hasattr(exc, 'error_dict'):
        for field_name, errors in exc.error_dict.items():
            target = field_name if field_name in form.fields else None
            for error in errors: form.add_error(target, error)
    else:
        for error in exc.messages: form.add_error(None, error)


class TransactionListView(BaseFinanceView, ListView):
    model = Transaction; template_name = 'finance/transaction_list.html'; context_object_name = 'transactions'
    def get_paginate_by(self, queryset):
        try:
            size = int(self.request.GET.get('page_size', '25')); return size if 1 <= size <= 200 else 25
        except (TypeError, ValueError): return 25
    def get_queryset(self):
        qs = Transaction.objects.filter(account=self.request.account, financial_year=self.request.fy).select_related('account','financial_year','account_head','sub_head','major_head','outflow_nature','inflow_type','unit').prefetch_related('transaction_units','transaction_sections')
        filters = {'direction':self.request.GET.get('direction'),'major_head_id':self.request.GET.get('major_head'),'sub_head_id':self.request.GET.get('sub_head'),'account_head_id':self.request.GET.get('account_head'),'outflow_nature_id':self.request.GET.get('nature'),'status':self.request.GET.get('status')}
        for key,value in filters.items():
            if value: qs = qs.filter(**{key:value})
        unit_val = self.request.GET.get('unit')
        if unit_val:
            qs = qs.filter(Q(unit_id=unit_val) | Q(transaction_units__id=unit_val)).distinct()
        pass_through = self.request.GET.get('pass_through')
        if pass_through in ('True','true','1'): qs = qs.filter(pass_through=True)
        elif pass_through in ('False','false','0'): qs = qs.filter(pass_through=False)
        if self.request.GET.get('date_from'): qs = qs.filter(transaction_date__gte=self.request.GET['date_from'])
        if self.request.GET.get('date_to'): qs = qs.filter(transaction_date__lte=self.request.GET['date_to'])
        month_filter = self.request.GET.get('month')
        if month_filter:
            m_parts = month_filter.strip().split('-')
            if len(m_parts) == 2 and m_parts[0].isdigit() and m_parts[1].isdigit():
                qs = qs.filter(transaction_date__year=int(m_parts[0]), transaction_date__month=int(m_parts[1]))
        q = self.request.GET.get('q','').strip()
        if q: qs = qs.filter(Q(transaction_number__icontains=q)|Q(description__icontains=q)|Q(purpose__icontains=q)|Q(payee_or_source__icontains=q)|Q(reference__icontains=q)|Q(document_reference__icontains=q))
        return qs
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        ctx['total_inflows'] = qs.filter(direction=Transaction.Direction.INFLOW, status__in=[Transaction.Status.ACTIVE, Transaction.Status.DRAFT]).aggregate(total=Sum('amount'))['total'] or 0
        ctx['total_outflows'] = qs.filter(direction=Transaction.Direction.OUTFLOW, status__in=[Transaction.Status.ACTIVE, Transaction.Status.DRAFT], pass_through=False).aggregate(total=Sum('amount'))['total'] or 0
        ctx['total_pass_through'] = qs.filter(direction=Transaction.Direction.OUTFLOW, status__in=[Transaction.Status.ACTIVE, Transaction.Status.DRAFT], pass_through=True).aggregate(total=Sum('amount'))['total'] or 0
        ctx['gross_outflows'] = (ctx['total_outflows'] or 0) + (ctx['total_pass_through'] or 0)
        ctx['record_count'] = qs.count()
        ctx['accounts'] = [self.request.account]
        ctx['financial_years'] = [self.request.fy]
        query_params = self.request.GET.copy()
        if 'page' in query_params:
            del query_params['page']
        ctx['query_string'] = query_params.urlencode()

        major_heads_qs = MajorHead.objects.filter(Q(account=self.request.account) | Q(account__isnull=True), is_active=True).order_by('display_order', 'name')
        sub_heads_qs = SubHead.objects.filter(Q(account=self.request.account) | Q(account__isnull=True), is_active=True).order_by('display_order', 'name')
        account_heads_qs = AccountHead.objects.filter(account=self.request.account, is_active=True).order_by('display_order', 'name')
        units_qs = Unit.objects.filter(is_active=True).order_by('display_order', 'name')
        internal_sections_qs = InternalSection.objects.filter(is_active=True).order_by('display_order', 'name')
        outflow_natures_qs = OutflowNature.objects.filter(is_active=True).order_by('display_order', 'name')
        inflow_types_qs = InflowType.objects.filter(Q(account=self.request.account) | Q(account__isnull=True), is_active=True).order_by('display_order', 'name')

        ctx['major_heads'] = major_heads_qs
        ctx['sub_heads'] = sub_heads_qs
        ctx['account_heads'] = account_heads_qs
        ctx['units'] = units_qs
        ctx['internal_sections'] = internal_sections_qs
        ctx['outflow_natures'] = outflow_natures_qs
        ctx['inflow_types'] = inflow_types_qs
        ctx['sub_fund_count'] = major_heads_qs.count()
        ctx['can_edit'] = self.request.user.is_superuser or (hasattr(self.request.user, 'profile') and self.request.user.profile.role != UserProfile.Role.MANAGEMENT)

        # Options dictionary for the dynamic inline table editor (serialized via json_script in template)
        ctx['ledger_options'] = {
            'major_heads': [{'id': mh.id, 'name': mh.name} for mh in major_heads_qs],
            'account_heads': [{'id': ah.id, 'name': ah.name, 'major_head_id': ah.major_head_id, 'head_type': ah.head_type} for ah in account_heads_qs],
            'sub_heads': [{'id': sh.id, 'name': sh.name, 'account_head_id': sh.account_head_id, 'major_head_id': sh.major_head_id} for sh in sub_heads_qs],
            'units': [{'id': u.id, 'name': u.name} for u in units_qs],
            'internal_sections': [{'id': s.id, 'name': s.name} for s in internal_sections_qs],
            'outflow_natures': [{'id': n.id, 'name': n.name} for n in outflow_natures_qs],
            'inflow_types': [{'id': it.id, 'name': it.name} for it in inflow_types_qs],
            'statuses': [
                {'id': Transaction.Status.ACTIVE, 'name': 'Active'},
                {'id': Transaction.Status.DRAFT, 'name': 'Draft'},
                {'id': Transaction.Status.CANCELLED, 'name': 'Cancelled'},
            ],
        }
        ctx['ledger_options_json'] = ctx['ledger_options']
        return ctx


class InflowCreateView(FinancialEditMixin, BaseFinanceView, CreateView):
    model=Transaction; form_class=InflowForm; template_name='finance/transaction_form.html'; success_url=reverse_lazy('core:transaction_list')
    def get_form_kwargs(self):
        kwargs=super().get_form_kwargs()
        kwargs['financial_year']=self.request.fy
        kwargs['account']=self.request.account
        return kwargs
    def get_context_data(self,**kwargs): ctx=super().get_context_data(**kwargs); ctx['title']='New Inflow'; return ctx
    def form_valid(self,form):
        form.instance.account=self.request.account; form.instance.financial_year=self.request.fy; form.instance.direction=Transaction.Direction.INFLOW; form.instance.created_by=self.request.user; assign_transaction_number(form.instance); form.instance.status=Transaction.Status.ACTIVE
        try: response=super().form_valid(form)
        except ValidationError as exc: _add_model_validation_errors(form,exc); return self.form_invalid(form)
        handle_document_upload(self.request,self.object); log_audit_action(self.request.user,'CREATE_INFLOW',self.object,account=self.request.account); messages.success(self.request,f'Transaction saved successfully. Transaction Number: {self.object.transaction_number}'); return response


class OutflowCreateView(FinancialEditMixin, BaseFinanceView, CreateView):
    model=Transaction; form_class=OutflowForm; template_name='finance/transaction_form.html'; success_url=reverse_lazy('core:transaction_list')
    def get_form_kwargs(self):
        kwargs=super().get_form_kwargs()
        kwargs['financial_year']=self.request.fy
        kwargs['account']=self.request.account
        return kwargs
    def get_context_data(self,**kwargs): ctx=super().get_context_data(**kwargs); ctx['title']='New Outflow'; return ctx
    def form_valid(self,form):
        form.instance.account=self.request.account; form.instance.financial_year=self.request.fy; form.instance.direction=Transaction.Direction.OUTFLOW; form.instance.created_by=self.request.user; assign_transaction_number(form.instance); form.instance.status=Transaction.Status.ACTIVE
        if form.instance.sub_head and form.instance.sub_head.major_head: form.instance.major_head=form.instance.sub_head.major_head
        elif form.instance.account_head and form.instance.account_head.major_head: form.instance.major_head=form.instance.account_head.major_head
        try: response=super().form_valid(form)
        except ValidationError as exc: _add_model_validation_errors(form,exc); return self.form_invalid(form)
        handle_document_upload(self.request,self.object); log_audit_action(self.request.user,'CREATE_OUTFLOW',self.object,account=self.request.account); messages.success(self.request,f'Transaction saved successfully. Transaction Number: {self.object.transaction_number}'); return response


class InternalTransferCreateView(FinancialEditMixin, BaseFinanceView, FormView):
    form_class = InternalTransferForm
    template_name = 'finance/internal_transfer_form.html'
    success_url = reverse_lazy('core:internal_transfer_create')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['account'] = self.request.account
        kwargs['financial_year'] = self.request.fy
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        from_mh = self.request.GET.get('from_mh')
        to_mh = self.request.GET.get('to_mh')
        if from_mh:
            initial['source_major_head'] = from_mh
        if to_mh:
            initial['dest_major_head'] = to_mh
        return initial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Sub-Fund Distribution & Inter-Transfers'
        from .services import get_sub_fund_distribution_summary
        ctx['distribution'] = get_sub_fund_distribution_summary(self.request.account, self.request.fy)
        return ctx

    def form_valid(self, form):
        account = self.request.account
        fy = self.request.fy
        user = self.request.user

        t_date = form.cleaned_data['transaction_date']
        amount = form.cleaned_data['amount']
        ref = form.cleaned_data['sanction_reference'].strip()
        desc = form.cleaned_data.get('description', '').strip()

        src_mh = form.cleaned_data['source_major_head']
        src_ah = form.cleaned_data['source_account_head']
        src_sh = form.cleaned_data.get('source_sub_head')

        dst_mh = form.cleaned_data['dest_major_head']
        dst_ah = form.cleaned_data['dest_account_head']
        dst_sh = form.cleaned_data.get('dest_sub_head')

        remarks_user = f" | {desc}" if desc else ""

        try:
            with transaction.atomic():
                # 1. Source (OUTFLOW / Debit from Source Head)
                outflow_tx = Transaction(
                    account=account,
                    financial_year=fy,
                    direction=Transaction.Direction.OUTFLOW,
                    transaction_date=t_date,
                    amount=amount,
                    major_head=src_mh,
                    account_head=src_ah,
                    sub_head=src_sh,
                    pass_through=True,
                    payee_or_source=f"Internal Transfer To: {dst_mh.name} ({dst_ah.name})",
                    description=f"Inter-Sub-Fund Transfer To: {dst_mh.name} - {dst_ah.name} (Ref: {ref}){remarks_user}",
                    purpose=f"Inter-Head Transfer To: {dst_ah.name}",
                    reference=ref,
                    status=Transaction.Status.ACTIVE,
                    created_by=user,
                )
                assign_transaction_number(outflow_tx)
                outflow_tx.save()

                # 2. Destination (INFLOW / Credit to Destination Head)
                inflow_tx = Transaction(
                    account=account,
                    financial_year=fy,
                    direction=Transaction.Direction.INFLOW,
                    transaction_date=t_date,
                    amount=amount,
                    major_head=dst_mh,
                    account_head=dst_ah,
                    sub_head=dst_sh,
                    pass_through=True,
                    payee_or_source=f"Internal Transfer From: {src_mh.name} ({src_ah.name})",
                    description=f"Inter-Sub-Fund Transfer From: {src_mh.name} - {src_ah.name} (Ref: {ref}){remarks_user}",
                    purpose=f"Inter-Head Transfer From: {src_ah.name}",
                    reference=ref,
                    status=Transaction.Status.ACTIVE,
                    created_by=user,
                )
                assign_transaction_number(inflow_tx)
                inflow_tx.document_reference = f"Contra: {outflow_tx.transaction_number}"
                inflow_tx.save()

                # Update outflow cross-reference
                outflow_tx.document_reference = f"Contra: {inflow_tx.transaction_number}"
                outflow_tx.save(update_fields=['document_reference'])

                log_audit_action(user, 'CREATE_INTERNAL_TRANSFER', outflow_tx, account=account)
                log_audit_action(user, 'CREATE_INTERNAL_TRANSFER', inflow_tx, account=account)
        except ValidationError as exc:
            _add_model_validation_errors(form, exc)
            return self.form_invalid(form)

        messages.success(
            self.request,
            f"Inter-Sub-Fund Transfer of Rs {amount:,.2f} posted successfully! "
            f"Reallocated from {src_mh.name} ({src_ah.name}) to {dst_mh.name} ({dst_ah.name}). "
            f"Created Debit Txn ({outflow_tx.transaction_number}) and Credit Txn ({inflow_tx.transaction_number}) "
            f"with Pass-Through classification (0 net cash impact)."
        )
        return redirect('core:internal_transfer_create')


class TransactionDetailView(BaseFinanceView, DetailView):
    model=Transaction; template_name='finance/transaction_detail.html'; context_object_name='transaction'
    def get_object(self,queryset=None): return get_object_or_404(Transaction,pk=self.kwargs['pk'],account=self.request.account)
    def get_context_data(self,**kwargs): ctx=super().get_context_data(**kwargs); ctx['documents']=DocumentLink.objects.filter(entity_type='TRANSACTION',entity_id=str(self.object.id)); ctx['reimbursements']=Reimbursement.objects.filter(original_outflow=self.object); return ctx


class TransactionUpdateView(FinancialEditMixin, BaseFinanceView, UpdateView):
    model=Transaction; template_name='finance/transaction_form.html'; success_url=reverse_lazy('core:transaction_list')
    def get_queryset(self): return Transaction.objects.filter(account=self.request.account)
    def get_form_class(self): return InflowForm if self.object.direction==Transaction.Direction.INFLOW else OutflowForm
    def get_form_kwargs(self):
        kwargs=super().get_form_kwargs()
        kwargs['financial_year']=self.request.fy
        kwargs['account']=self.request.account
        return kwargs
    def get_context_data(self,**kwargs): ctx=super().get_context_data(**kwargs); ctx['title']=f'Edit {self.object.get_direction_display()}'; return ctx
    def dispatch(self,request,*args,**kwargs):
        obj=self.get_object()
        if obj.status==Transaction.Status.CANCELLED:
            messages.error(request,'Cancelled transactions are read-only.')
            return redirect('core:transaction_detail',pk=obj.id)
        return super().dispatch(request,*args,**kwargs)
    def form_valid(self,form):
        form.instance.updated_by=self.request.user; assign_transaction_number(form.instance)
        if getattr(form.instance,'sub_head',None) and form.instance.sub_head.major_head: form.instance.major_head=form.instance.sub_head.major_head
        try: response=super().form_valid(form)
        except ValidationError as exc: _add_model_validation_errors(form,exc); return self.form_invalid(form)
        handle_document_upload(self.request,self.object); log_audit_action(self.request.user,'UPDATE_TRANSACTION',self.object,account=self.request.account); messages.success(self.request,'Transaction updated successfully.'); return response


class ReimbursementListView(BaseFinanceView,ListView):
    model=Reimbursement; template_name='finance/reimbursement_list.html'; context_object_name='reimbursements'
    def get_queryset(self): return Reimbursement.objects.filter(original_outflow__account=self.request.account,original_outflow__financial_year=self.request.fy).select_related('reimbursement_type','original_outflow','received_inflow')


class ReimbursementCreateView(FinancialEditMixin,BaseFinanceView,CreateView):
    model=Reimbursement; form_class=ReimbursementForm; template_name='finance/reimbursement_form.html'; success_url=reverse_lazy('core:reimbursement_list')
    def get_context_data(self,**kwargs): ctx=super().get_context_data(**kwargs); ctx['title']='New Reimbursement'; return ctx
    def form_valid(self,form): form.instance.created_by=self.request.user; response=super().form_valid(form); handle_document_upload(self.request,self.object,entity_type='REIMBURSEMENT'); log_audit_action(self.request.user,'CREATE_REIMBURSEMENT',self.object,account=self.request.account); messages.success(self.request,'Reimbursement saved successfully.'); return response


class ReimbursementUpdateView(FinancialEditMixin,BaseFinanceView,UpdateView):
    model=Reimbursement; form_class=ReimbursementForm; template_name='finance/reimbursement_form.html'; success_url=reverse_lazy('core:reimbursement_list')
    def get_queryset(self): return Reimbursement.objects.filter(original_outflow__account=self.request.account,original_outflow__financial_year=self.request.fy)
    def get_context_data(self,**kwargs): ctx=super().get_context_data(**kwargs); ctx['title']='Edit Reimbursement'; return ctx
    def form_valid(self,form): response=super().form_valid(form); handle_document_upload(self.request,self.object,entity_type='REIMBURSEMENT'); log_audit_action(self.request.user,'UPDATE_REIMBURSEMENT',self.object,account=self.request.account); messages.success(self.request,'Reimbursement updated successfully.'); return response


class TransactionInlineUpdateView(FinancialEditMixin, View):
    def post(self, request, pk, *args, **kwargs):
        tx = Transaction.objects.filter(pk=pk).first()
        if not tx:
            return JsonResponse({'status': 'error', 'message': 'Transaction not found.'}, status=404)

        profile = getattr(request.user, 'profile', None)
        if profile and profile.role == UserProfile.Role.MANAGEMENT:
            return JsonResponse({'status': 'error', 'message': 'Management role cannot edit transactions.'}, status=403)

        data = request.POST
        if not data and request.body:
            try:
                data = json.loads(request.body.decode('utf-8'))
            except Exception:
                pass

        # Check cancelled status: only Administrator can edit cancelled transactions
        can_manage_cancelled = request.user.is_superuser or (profile and profile.role == UserProfile.Role.ADMINISTRATOR)
        status_val = data.get('status')
        if tx.status == Transaction.Status.CANCELLED and not can_manage_cancelled and status_val != Transaction.Status.ACTIVE:
            return JsonResponse({'status': 'error', 'message': 'Cancelled transactions cannot be edited except by an Administrator.'}, status=400)

        # 1. Transaction Date
        date_raw = data.get('transaction_date')
        if date_raw:
            date_str = str(date_raw).strip()
            parsed_date = None
            for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%Y/%m/%d'):
                try:
                    parsed_date = datetime.strptime(date_str, fmt).date()
                    break
                except ValueError:
                    continue
            if parsed_date:
                tx.transaction_date = parsed_date

        # 2. Reference
        ref = data.get('reference')
        if ref is not None:
            tx.reference = ref.strip()

        # 3. Payee / Source
        payee = data.get('payee_or_source')
        if payee is not None:
            tx.payee_or_source = payee.strip()

        # 4. Description
        desc = data.get('description')
        if desc is not None:
            tx.description = desc.strip()

        # 5. Amount
        amount_raw = data.get('amount')
        if amount_raw is not None and str(amount_raw).strip():
            try:
                amt = Decimal(str(amount_raw).replace(',', '').strip())
                if amt <= 0:
                    return JsonResponse({'status': 'error', 'message': 'Amount must be strictly positive.'}, status=400)
                tx.amount = amt
            except (InvalidOperation, ValueError):
                return JsonResponse({'status': 'error', 'message': 'Invalid amount value.'}, status=400)

        # 6. Status
        if status_val in dict(Transaction.Status.choices):
            tx.status = status_val

        # 7. Pass-Through
        if 'pass_through' in data:
            pt_val = str(data.get('pass_through')).lower().strip()
            tx.pass_through = pt_val in ('true', '1', 'yes', 'on')

        # 8. Major Head (Sub Fund - Tier 1)
        major_head_id = data.get('major_head_id')
        if major_head_id:
            mh = MajorHead.objects.filter(id=major_head_id).first()
            if mh:
                tx.major_head = mh
        elif major_head_id == '':
            tx.major_head = None

        # 9. Account Head (Tier 2)
        account_head_id = data.get('account_head_id')
        if account_head_id:
            ah = AccountHead.objects.filter(id=account_head_id, account=tx.account).first()
            if ah:
                tx.account_head = ah
                if not major_head_id and ah.major_head:
                    tx.major_head = ah.major_head

        # 10. Sub Head (Tier 3)
        sub_head_id = data.get('sub_head_id')
        if sub_head_id:
            sh = SubHead.objects.filter(id=sub_head_id).first()
            if sh:
                tx.sub_head = sh
        elif sub_head_id == '':
            tx.sub_head = None

        # 11. Unit
        unit_id = data.get('unit_id')
        if unit_id:
            u = Unit.objects.filter(id=unit_id).first()
            if u:
                tx.unit = u
        elif unit_id == '':
            tx.unit = None

        # 12. Internal Section
        internal_section_id = data.get('internal_section_id')
        if internal_section_id:
            sec = InternalSection.objects.filter(id=internal_section_id).first()
            if sec:
                tx.internal_section = sec
        elif internal_section_id == '':
            tx.internal_section = None

        # 13. Outflow Nature
        if tx.direction == Transaction.Direction.OUTFLOW:
            nature_id = data.get('outflow_nature_id')
            if nature_id:
                nat = OutflowNature.objects.filter(id=nature_id).first()
                if nat:
                    tx.outflow_nature = nat
            elif nature_id == '':
                tx.outflow_nature = None

        # 14. Inflow Type
        if tx.direction == Transaction.Direction.INFLOW:
            inflow_type_id = data.get('inflow_type_id')
            if inflow_type_id:
                it = InflowType.objects.filter(id=inflow_type_id).first()
                if it:
                    tx.inflow_type = it
            elif inflow_type_id == '':
                tx.inflow_type = None

        try:
            tx.updated_by = request.user
            tx.clean()
            tx.save()

            # Sync ManyToMany relations
            if unit_id is not None:
                if unit_id and tx.unit:
                    tx.transaction_units.set([tx.unit])
                else:
                    tx.transaction_units.clear()
            if internal_section_id is not None:
                if internal_section_id and tx.internal_section:
                    tx.transaction_sections.set([tx.internal_section])
                else:
                    tx.transaction_sections.clear()

            log_audit_action(request.user, 'INLINE_UPDATE_TRANSACTION', tx, account=tx.account)

            units_display = [u.name for u in tx.transaction_units.all()]
            if not units_display and tx.unit:
                units_display = [tx.unit.name]

            sections_display = [s.name for s in tx.transaction_sections.all()]
            if not sections_display and tx.internal_section:
                sections_display = [tx.internal_section.name]

            return JsonResponse({
                'status': 'ok',
                'id': str(tx.id),
                'transaction_number': tx.transaction_number,
                'transaction_date': tx.transaction_date.strftime('%Y-%m-%d') if tx.transaction_date else '',
                'transaction_date_display': tx.transaction_date.strftime('%d-%m-%Y') if tx.transaction_date else '',
                'reference': tx.reference or '',
                'payee_or_source': tx.payee_or_source or '',
                'description': tx.description or tx.purpose or '',
                'amount': f'{tx.amount:.2f}',
                'direction': tx.direction,
                'pass_through': tx.pass_through,
                'major_head_id': tx.major_head_id or '',
                'major_head_name': tx.major_head.name if tx.major_head else '',
                'account_head_id': tx.account_head_id or '',
                'account_head_name': tx.account_head.name if tx.account_head else '',
                'sub_head_id': tx.sub_head_id or '',
                'sub_head_name': tx.sub_head.name if tx.sub_head else '',
                'unit_id': tx.unit_id or '',
                'unit_name': tx.unit.name if tx.unit else '',
                'units': units_display,
                'internal_section_id': tx.internal_section_id or '',
                'internal_section_name': tx.internal_section.name if tx.internal_section else '',
                'sections': sections_display,
                'outflow_nature_id': tx.outflow_nature_id or '',
                'outflow_nature_name': tx.outflow_nature.name if tx.outflow_nature else '',
                'inflow_type_id': tx.inflow_type_id or '',
                'inflow_type_name': tx.inflow_type.name if tx.inflow_type else '',
                'tx_status': tx.status,
                'status_display': tx.get_status_display(),
            })
        except ValidationError as ve:
            msg = '; '.join([f"{k}: {', '.join(v) if isinstance(v, list) else v}" for k, v in ve.message_dict.items()]) if hasattr(ve, 'message_dict') else str(ve)
            return JsonResponse({'status': 'error', 'message': msg}, status=400)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
