from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views import View

from .models import Transaction
from .services import log_audit_action


class TransactionCancelView(View):
    def post(self, request, *args, **kwargs):
        transaction = get_object_or_404(
            Transaction,
            pk=kwargs['pk'],
            account=request.account,
            financial_year=request.fy,
        )
        if transaction.status == Transaction.Status.CANCELLED:
            messages.info(request, 'Transaction is already cancelled.')
            return redirect('core:transaction_detail', pk=transaction.id)
        if transaction.is_historical:
            messages.error(request, 'Historical transactions cannot be cancelled directly.')
            return redirect('core:transaction_detail', pk=transaction.id)

        transaction.status = Transaction.Status.CANCELLED
        transaction.updated_by = request.user
        transaction.save(update_fields=['status', 'updated_by', 'updated_at'])
        log_audit_action(request.user, 'CANCEL_TRANSACTION', transaction, account=request.account)
        messages.success(request, 'Transaction cancelled successfully.')
        return redirect('core:transaction_detail', pk=transaction.id)
