from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from .models import Transaction, Unit, InternalSection, Account
from .services import log_audit_action


class TransactionDataAdministrationView(LoginRequiredMixin, View):
    template_name = 'finance/data_administration.html'

    def dispatch(self, request, *args, **kwargs):
        profile = getattr(request.user, 'profile', None)
        if not profile or profile.role not in ['ADMINISTRATOR', 'MANAGEMENT']:
            raise PermissionDenied('Only Administrator or Management may access transaction data administration.')
        return super().dispatch(request, *args, **kwargs)

    def _filtered_queryset(self, request, include_deleted=False):
        qs = Transaction.objects.select_related('account', 'financial_year', 'account_head')
        if not include_deleted:
            qs = qs.exclude(status=Transaction.Status.SOFT_DELETED)
        
        # Always isolate to current account unless explicitly provided
        acc_id = request.GET.get('account') or (request.account.id if hasattr(request, 'account') and request.account else None)
        if acc_id:
            qs = qs.filter(account_id=acc_id)

        if request.GET.get('financial_year'):
            qs = qs.filter(financial_year_id=request.GET['financial_year'])
        if request.GET.get('date_from'):
            qs = qs.filter(transaction_date__gte=request.GET['date_from'])
        if request.GET.get('date_to'):
            qs = qs.filter(transaction_date__lte=request.GET['date_to'])
        if request.GET.get('unit'):
            qs = qs.filter(transaction_units__id=request.GET['unit'])
        if request.GET.get('section'):
            qs = qs.filter(transaction_sections__id=request.GET['section'])
        return qs.distinct()

    def get(self, request):
        qs = self._filtered_queryset(request)
        is_filtered = bool(request.GET.get('date_from') or request.GET.get('date_to') or request.GET.get('unit') or request.GET.get('section') or request.GET.get('financial_year'))
        context = {
            'transactions': qs[:100],
            'record_count': qs.count(),
            'is_filtered': is_filtered,
            'inflow_total': qs.filter(direction=Transaction.Direction.INFLOW).aggregate(v=Sum('amount'))['v'] or Decimal('0.00'),
            'outflow_total': qs.filter(direction=Transaction.Direction.OUTFLOW).aggregate(v=Sum('amount'))['v'] or Decimal('0.00'),
            'units': Unit.objects.filter(is_active=True),
            'sections': InternalSection.objects.filter(is_active=True),
            'accounts': Account.objects.filter(is_active=True).order_by('name'),
            'query': request.GET,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        qs = self._filtered_queryset(request)
        if request.POST.get('action') == 'soft_delete':
            reason = request.POST.get('reason', '').strip()
            if not reason:
                messages.error(request, 'Deletion reason is mandatory.')
                return redirect(request.get_full_path())
            count = 0
            now = timezone.now()
            for tx in qs.iterator():
                tx.status = Transaction.Status.SOFT_DELETED
                tx.deleted_by = request.user
                tx.deleted_at = now
                tx.deletion_reason = reason
                tx.updated_by = request.user
                tx.save(update_fields=['status', 'deleted_by', 'deleted_at', 'deletion_reason', 'updated_by', 'updated_at'])
                log_audit_action(request.user, 'SOFT_DELETE_TRANSACTION', tx, account=tx.account)
                count += 1
            messages.success(request, f'{count} transaction(s) soft-deleted. No physical records were destroyed.')
        return redirect('core:data_administration')


class TransactionRestoreView(LoginRequiredMixin, View):
    def post(self, request, pk):
        profile = getattr(request.user, 'profile', None)
        if not profile or profile.role != 'ADMINISTRATOR':
            raise PermissionDenied('Only Administrator may restore soft-deleted transactions.')
        tx = get_object_or_404(Transaction, pk=pk, status=Transaction.Status.SOFT_DELETED)
        tx.status = Transaction.Status.ACTIVE
        tx.updated_by = request.user
        tx.deleted_by = None
        tx.deleted_at = None
        tx.deletion_reason = ''
        tx.save(update_fields=['status', 'updated_by', 'deleted_by', 'deleted_at', 'deletion_reason', 'updated_at'])
        log_audit_action(request.user, 'RESTORE_TRANSACTION', tx, account=tx.account)
        messages.success(request, f'{tx.transaction_number} restored.')
        return redirect('core:data_administration')
