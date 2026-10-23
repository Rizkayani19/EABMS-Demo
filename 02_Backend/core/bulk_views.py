import json
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction as db_transaction
from django.db.models import ProtectedError
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.views import View

from .models import (
    Budget,
    BudgetLine,
    FutureBudget,
    FutureBudgetKnownChange,
    FutureBudgetLine,
    FutureBudgetPersonnel,
    Reimbursement,
    Transaction,
    UserProfile,
)
from .services import log_audit_action


def _can_modify(request):
    if request.user.is_superuser:
        return True
    profile = getattr(request.user, 'profile', None)
    return bool(profile and profile.role in [UserProfile.Role.ADMINISTRATOR, UserProfile.Role.CLERK])


def _extract_ids(request):
    """Extract list of IDs from POST request (handles multiple selected_ids, comma strings, or JSON)."""
    ids = request.POST.getlist('selected_ids') or request.POST.getlist('ids')
    if not ids:
        raw = request.POST.get('selected_ids') or request.POST.get('ids') or ''
        if raw.startswith('[') and raw.endswith(']'):
            try:
                ids = json.loads(raw)
            except Exception:
                ids = []
        elif raw:
            ids = [i.strip() for i in raw.split(',') if i.strip()]
    return [i for i in ids if i]


class TransactionBulkDeleteView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        is_json = request.content_type == 'application/json' or 'application/json' in request.headers.get('Accept', '')

        if not _can_modify(request):
            if is_json:
                return HttpResponseForbidden(json.dumps({'ok': False, 'message': 'You do not have permission to delete transactions.'}), content_type='application/json')
            raise PermissionDenied("You do not have permission to delete transactions.")

        if is_json and request.body:
            try:
                body_data = json.loads(request.body.decode('utf-8') or '{}')
                ids = body_data.get('ids') or body_data.get('selected_ids') or []
            except Exception:
                ids = []
        else:
            ids = _extract_ids(request)

        if not ids:
            if is_json:
                return JsonResponse({'ok': False, 'message': 'No transactions were selected for deletion.'}, status=400)
            messages.warning(request, "No transactions were selected for deletion.")
            return redirect(request.META.get('HTTP_REFERER') or 'core:transaction_list')

        account = getattr(request, 'account', None)
        qs = Transaction.objects.filter(id__in=ids)
        if account:
            qs = qs.filter(account=account)

        deleted_count = 0
        protected_historical_count = 0
        deleted_ids = []

        with db_transaction.atomic():
            for tx in qs:
                if tx.is_historical:
                    protected_historical_count += 1
                    continue
                # Log audit before deletion
                log_audit_action(
                    actor=request.user,
                    action='DELETE_TRANSACTION',
                    instance=tx,
                    account=tx.account,
                )
                deleted_ids.append(str(tx.id))
                tx.delete()
                deleted_count += 1

        if is_json:
            return JsonResponse({
                'ok': True,
                'deleted_count': deleted_count,
                'protected_count': protected_historical_count,
                'deleted_ids': deleted_ids,
                'message': f"Successfully deleted {deleted_count} transaction(s)." + (f" ({protected_historical_count} historical transactions were protected and skipped.)" if protected_historical_count else "")
            })

        if deleted_count > 0:
            messages.success(request, f"Successfully deleted {deleted_count} transaction(s).")
        if protected_historical_count > 0:
            messages.warning(request, f"{protected_historical_count} historical transaction(s) were protected and could not be deleted.")
        if deleted_count == 0 and protected_historical_count == 0:
            messages.info(request, "No matching transactions found to delete.")

        return redirect(request.META.get('HTTP_REFERER') or 'core:transaction_list')


class ReimbursementBulkDeleteView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        if not _can_modify(request):
            raise PermissionDenied("You do not have permission to delete reimbursements.")

        ids = _extract_ids(request)
        if not ids:
            messages.warning(request, "No reimbursements were selected for deletion.")
            return redirect(request.META.get('HTTP_REFERER') or 'core:reimbursement_list')

        from django.db.models import Q
        account = getattr(request, 'account', None)
        qs = Reimbursement.objects.filter(id__in=ids)
        if account:
            qs = qs.filter(Q(original_outflow__account=account) | Q(original_outflow__isnull=True))

        deleted_count = 0
        for r in qs:
            log_audit_action(actor=request.user, action='DELETE_REIMBURSEMENT', instance=r, account=r.original_outflow.account if r.original_outflow else account)
            r.delete()
            deleted_count += 1

        if deleted_count > 0:
            messages.success(request, f"Successfully deleted {deleted_count} reimbursement(s).")
        else:
            messages.info(request, "No matching reimbursements found to delete.")

        return redirect(request.META.get('HTTP_REFERER') or 'core:reimbursement_list')


class BudgetBulkDeleteView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        if not _can_modify(request):
            raise PermissionDenied("You do not have permission to delete budgets.")

        ids = _extract_ids(request)
        if not ids:
            messages.warning(request, "No budgets were selected for deletion.")
            return redirect(request.META.get('HTTP_REFERER') or 'core:budget_list')

        account = getattr(request, 'account', None)
        qs = Budget.objects.filter(id__in=ids)
        if account:
            qs = qs.filter(account=account)

        deleted_count = 0
        for b in qs:
            log_audit_action(actor=request.user, action='DELETE_BUDGET', instance=b, account=b.account)
            b.delete()
            deleted_count += 1

        if deleted_count > 0:
            messages.success(request, f"Successfully deleted {deleted_count} budget(s).")
        else:
            messages.info(request, "No matching budgets found to delete.")

        return redirect(request.META.get('HTTP_REFERER') or 'core:budget_list')


class BudgetLineBulkDeleteView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        if not _can_modify(request):
            raise PermissionDenied("You do not have permission to delete budget lines.")

        budget_id = kwargs.get('budget_id')
        budget = get_object_or_404(Budget, pk=budget_id, account=request.account) if budget_id else None

        ids = _extract_ids(request)
        if not ids:
            messages.warning(request, "No budget lines were selected for deletion.")
            return redirect(request.META.get('HTTP_REFERER') or ('core:budget_detail', budget.pk) if budget else 'core:budget_list')

        qs = BudgetLine.objects.filter(id__in=ids)
        if budget:
            qs = qs.filter(budget=budget)

        deleted_count = 0
        for bl in qs:
            log_audit_action(actor=request.user, action='DELETE_BUDGET_LINE', instance=bl, account=bl.budget.account if bl.budget else None)
            bl.delete()
            deleted_count += 1

        if deleted_count > 0:
            messages.success(request, f"Successfully deleted {deleted_count} budget line(s).")
        else:
            messages.info(request, "No matching budget lines found to delete.")

        referer = request.META.get('HTTP_REFERER')
        if referer:
            return redirect(referer)
        if budget:
            return redirect('core:budget_detail', pk=budget.pk)
        return redirect('core:budget_list')


class FutureBudgetBulkDeleteView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        if not _can_modify(request):
            raise PermissionDenied("You do not have permission to delete future budgets.")

        ids = _extract_ids(request)
        if not ids:
            messages.warning(request, "No future budgets were selected for deletion.")
            return redirect(request.META.get('HTTP_REFERER') or 'core:future_budget_list')

        account = getattr(request, 'account', None)
        qs = FutureBudget.objects.filter(id__in=ids)
        if account:
            qs = qs.filter(account=account)

        deleted_count = 0
        for fb in qs:
            log_audit_action(actor=request.user, action='DELETE_FUTURE_BUDGET', instance=fb, account=fb.account)
            fb.delete()
            deleted_count += 1

        if deleted_count > 0:
            messages.success(request, f"Successfully deleted {deleted_count} future budget(s).")
        else:
            messages.info(request, "No matching future budgets found to delete.")

        return redirect(request.META.get('HTTP_REFERER') or 'core:future_budget_list')


class FutureBudgetLineBulkDeleteView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        if not _can_modify(request):
            raise PermissionDenied("You do not have permission to delete future budget lines.")

        budget_id = kwargs.get('future_budget_id') or kwargs.get('budget_id')
        fb = get_object_or_404(FutureBudget, pk=budget_id, account=request.account) if budget_id else None

        ids = _extract_ids(request)
        if not ids:
            messages.warning(request, "No future budget lines were selected for deletion.")
            referer = request.META.get('HTTP_REFERER')
            if referer:
                return redirect(referer)
            if fb:
                return redirect('core:future_budget_detail', pk=fb.pk)
            return redirect('core:future_budget_list')

        qs = FutureBudgetLine.objects.filter(id__in=ids)
        if fb:
            qs = qs.filter(future_budget=fb)

        deleted_count = 0
        for fbl in qs:
            log_audit_action(actor=request.user, action='DELETE_FUTURE_BUDGET_LINE', instance=fbl, account=fbl.future_budget.account if fbl.future_budget else None)
            fbl.delete()
            deleted_count += 1

        if deleted_count > 0:
            messages.success(request, f"Successfully deleted {deleted_count} future budget line(s).")
        else:
            messages.info(request, "No matching future budget lines found to delete.")

        referer = request.META.get('HTTP_REFERER')
        if referer:
            return redirect(referer)
        if fb:
            return redirect('core:future_budget_detail', pk=fb.pk)
        return redirect('core:future_budget_list')


class FutureBudgetKnownChangeBulkDeleteView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        if not _can_modify(request):
            raise PermissionDenied("You do not have permission to delete known changes.")

        ids = _extract_ids(request)
        if not ids:
            messages.warning(request, "No known changes selected for deletion.")
            return redirect(request.META.get('HTTP_REFERER') or 'core:future_budget_list')

        qs = FutureBudgetKnownChange.objects.filter(id__in=ids)
        deleted_count = 0
        for kc in qs:
            log_audit_action(actor=request.user, action='DELETE_KNOWN_CHANGE', instance=kc, account=kc.future_budget.account if kc.future_budget else None)
            kc.delete()
            deleted_count += 1

        if deleted_count > 0:
            messages.success(request, f"Successfully deleted {deleted_count} known change(s).")

        return redirect(request.META.get('HTTP_REFERER') or 'core:future_budget_list')


class FutureBudgetPersonnelBulkDeleteView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        if not _can_modify(request):
            raise PermissionDenied("You do not have permission to delete personnel lines.")

        ids = _extract_ids(request)
        if not ids:
            messages.warning(request, "No personnel lines selected for deletion.")
            return redirect(request.META.get('HTTP_REFERER') or 'core:future_budget_list')

        qs = FutureBudgetPersonnel.objects.filter(id__in=ids)
        deleted_count = 0
        for p in qs:
            log_audit_action(actor=request.user, action='DELETE_PERSONNEL_LINE', instance=p, account=p.future_budget.account if p.future_budget else None)
            p.delete()
            deleted_count += 1

        if deleted_count > 0:
            messages.success(request, f"Successfully deleted {deleted_count} personnel line(s).")

        return redirect(request.META.get('HTTP_REFERER') or 'core:future_budget_list')
