"""
ABMS bulk transaction editor.

High-productivity grid for non-historical Active/Draft transactions.
Business rules are intentionally delegated to Transaction.clean()/save().
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction as db_transaction
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import render
from django.views import View

from .models import (
    AccountHead,
    InflowType,
    InternalSection,
    MajorHead,
    OutflowNature,
    SubHead,
    Transaction,
    Unit,
    UserProfile,
)
from .services import get_active_account, get_active_fy, log_audit_action


def _role(request):
    profile = getattr(request.user, 'profile', None)
    return getattr(profile, 'role', None)


def _can_edit(request):
    return _role(request) in [UserProfile.Role.ADMINISTRATOR, UserProfile.Role.CLERK]


def _parse_date(value):
    if not value:
        raise ValueError('Date is required.')
    text = str(value).strip()
    for fmt in ('%d-%m-%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError('Date must be a valid date.')


def _parse_amount(value):
    if value in (None, ''):
        raise ValueError('Amount is required.')
    try:
        amount = Decimal(str(value).replace(',', '').strip()).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError('Amount must be a valid number with up to two decimals.') from exc
    if amount <= 0:
        raise ValueError('Amount must be greater than 0.00.')
    return amount


def _scope_queryset(request):
    account = get_active_account(request)
    fy = get_active_fy(request)
    qs = Transaction.objects.filter(
        account=account,
        financial_year=fy,
        is_historical=False,
        status__in=[Transaction.Status.ACTIVE, Transaction.Status.DRAFT],
    ).select_related('account_head', 'sub_head', 'unit', 'outflow_nature', 'inflow_type')

    month = request.GET.get('month')
    if month and month.isdigit() and 1 <= int(month) <= 12:
        qs = qs.filter(transaction_date__month=int(month))
    direction = request.GET.get('direction')
    if direction in [Transaction.Direction.INFLOW, Transaction.Direction.OUTFLOW]:
        qs = qs.filter(direction=direction)
    account_head = request.GET.get('account_head')
    if account_head:
        qs = qs.filter(account_head_id=account_head)
    q = request.GET.get('q', '').strip()
    if q:
        from django.db.models import Q
        qs = qs.filter(
            Q(transaction_number__icontains=q) |
            Q(reference__icontains=q) |
            Q(description__icontains=q) |
            Q(purpose__icontains=q) |
            Q(payee_or_source__icontains=q)
        )
    return account, fy, qs.order_by('-transaction_date', '-created_at')


def _option_payload(account):
    return {
        'account_heads': list(AccountHead.objects.filter(account=account, is_active=True).values('id', 'code', 'name', 'head_type', 'major_head_id')),
        'major_heads': list(MajorHead.objects.filter(account=account, is_active=True).values('id', 'code', 'name')),
        'sub_heads': list(SubHead.objects.filter(account=account, is_active=True).values('id', 'code', 'name', 'major_head_id')),
        'units': list(Unit.objects.filter(is_active=True).values('id', 'code', 'name')),
        'internal_sections': list(InternalSection.objects.filter(is_active=True).values('id', 'code', 'name')),
        'outflow_natures': list(OutflowNature.objects.filter(is_active=True).values('id', 'code', 'name')),
        'inflow_types': list(InflowType.objects.filter(is_active=True).values('id', 'code', 'name')),
    }


class TransactionBulkEditView(LoginRequiredMixin, View):
    template_name = 'finance/transaction_bulk_edit.html'

    def get(self, request, *args, **kwargs):
        account, fy, qs = _scope_queryset(request)
        rows = []
        for tx in qs[:500]:
            rows.append({
                'id': str(tx.id),
                'transaction_number': tx.transaction_number,
                'transaction_date': tx.transaction_date.strftime('%d-%m-%Y'),
                'direction': tx.direction,
                'amount': f'{tx.amount:.2f}',
                'account_head_id': tx.account_head_id,
                'major_head_id': tx.major_head_id,
                'sub_head_id': tx.sub_head_id,
                'unit_id': tx.unit_id,
                'internal_section_id': tx.internal_section_id,
                'outflow_nature_id': tx.outflow_nature_id,
                'inflow_type_id': tx.inflow_type_id,
                'pass_through': tx.pass_through,
                'payee_or_source': tx.payee_or_source,
                'reference': tx.reference,
                'description': tx.description,
                'remarks': tx.remarks,
                'status': tx.status,
            })
        context = {
            'account': account,
            'fy': fy,
            'rows': rows,
            'options': _option_payload(account),
            'month_choices': [(i, datetime(2000, i, 1).strftime('%B')) for i in range(1, 13)],
            'can_edit': _can_edit(request),
            'management_view': _role(request) == UserProfile.Role.MANAGEMENT,
        }
        return render(request, self.template_name, context)


class TransactionBulkSaveView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        if not _can_edit(request):
            return HttpResponseForbidden('Management users are view-only in the Bulk Transaction Grid.')

        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
            rows = payload.get('rows', [])
            if not isinstance(rows, list) or not rows:
                return JsonResponse({'ok': False, 'message': 'No rows were submitted.'}, status=400)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({'ok': False, 'message': 'Invalid request payload.'}, status=400)

        account = get_active_account(request)
        fy = get_active_fy(request)
        errors = []
        prepared = []
        existing_ids = [r.get('id') for r in rows if isinstance(r, dict) and r.get('id')]
        existing_map = {
            str(tx.id): tx for tx in Transaction.objects.filter(
                id__in=existing_ids,
                account=account,
                financial_year=fy,
                is_historical=False,
                status__in=[Transaction.Status.ACTIVE, Transaction.Status.DRAFT],
            )
        }

        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                errors.append({'row': idx, 'errors': ['Invalid row payload.']})
                continue
            row_errors = []
            try:
                is_update = bool(row.get('id'))
                if is_update:
                    tx = existing_map.get(str(row.get('id')))
                    if tx is None:
                        row_errors.append('Transaction was not found in the active Account/FY or is protected.')
                else:
                    tx = Transaction(account=account, financial_year=fy, created_by=request.user)

                if not row_errors:
                    tx.transaction_date = _parse_date(row.get('transaction_date'))
                    tx.direction = row.get('direction') or Transaction.Direction.OUTFLOW
                    tx.amount = _parse_amount(row.get('amount'))
                    tx.account_head_id = row.get('account_head_id') or None
                    tx.major_head_id = row.get('major_head_id') or None
                    tx.sub_head_id = row.get('sub_head_id') or None
                    tx.unit_id = row.get('unit_id') or None
                    tx.internal_section_id = row.get('internal_section_id') or None
                    tx.outflow_nature_id = row.get('nature_id') or row.get('outflow_nature_id') or None
                    tx.inflow_type_id = row.get('inflow_type_id') or None
                    tx.pass_through = bool(row.get('pass_through'))
                    tx.payee_or_source = str(row.get('payee_or_source') or '').strip()
                    tx.reference = str(row.get('reference') or '').strip()
                    tx.description = str(row.get('description') or '').strip()
                    tx.remarks = str(row.get('remarks') or '').strip()
                    tx.status = row.get('status') or Transaction.Status.ACTIVE
                    tx.updated_by = request.user
                    prepared.append((idx, tx, is_update))
            except ValueError as exc:
                row_errors.append(str(exc))
            except Exception as exc:
                row_errors.append(f'Validation preparation failed: {exc}')
            if row_errors:
                errors.append({'row': idx, 'id': row.get('id'), 'errors': row_errors})

        for idx, tx, is_update in prepared:
            try:
                tx.full_clean(exclude=['transaction_number'] if not tx.transaction_number else None)
            except Exception as exc:
                from django.core.exceptions import ValidationError
                if isinstance(exc, ValidationError):
                    row_error = []
                    if hasattr(exc, 'message_dict'):
                        for field, messages_ in exc.message_dict.items():
                            row_error.extend([f'{field}: {m}' for m in messages_])
                    else:
                        row_error.extend(exc.messages)
                    errors.append({'row': idx, 'id': str(tx.id) if tx.pk else None, 'errors': row_error})
                else:
                    errors.append({'row': idx, 'id': str(tx.id) if tx.pk else None, 'errors': [str(exc)]})

        if errors:
            return JsonResponse({'ok': False, 'success': False, 'message': 'No changes were saved. Correct the highlighted rows.', 'errors': errors}, status=400)

        saved = []
        updated_count = 0
        created_count = 0
        try:
            with db_transaction.atomic():
                for idx, tx, is_update in prepared:
                    old_values = None
                    if is_update:
                        current = existing_map[str(tx.id)]
                        old_values = {
                            'transaction_date': current.transaction_date.strftime('%d-%m-%Y'),
                            'direction': current.direction,
                            'amount': f'{current.amount:.2f}',
                            'account_head_id': current.account_head_id,
                            'sub_head_id': current.sub_head_id,
                            'unit_id': current.unit_id,
                            'payee_or_source': current.payee_or_source,
                            'reference': current.reference,
                            'description': current.description,
                            'remarks': current.remarks,
                        }
                        updated_count += 1
                    else:
                        created_count += 1

                    tx.save()
                    new_values = {
                        'transaction_date': tx.transaction_date.strftime('%d-%m-%Y'),
                        'direction': tx.direction,
                        'amount': f'{tx.amount:.2f}',
                        'account_head_id': tx.account_head_id,
                        'sub_head_id': tx.sub_head_id,
                        'unit_id': tx.unit_id,
                        'payee_or_source': tx.payee_or_source,
                        'reference': tx.reference,
                        'description': tx.description,
                        'remarks': tx.remarks,
                    }
                    log_audit_action(
                        request.user,
                        'BULK_UPDATE_TRANSACTION' if is_update else 'BULK_CREATE_TRANSACTION',
                        tx,
                        old_values=old_values,
                        new_values=new_values,
                        account=account,
                    )
                    saved.append({'row': idx, 'id': str(tx.id), 'transaction_number': tx.transaction_number})
        except Exception as exc:
            return JsonResponse({'ok': False, 'success': False, 'message': f'Batch save failed; no changes were committed. {exc}'}, status=500)

        return JsonResponse({
            'ok': True,
            'success': True,
            'message': f'{len(saved)} transaction row(s) saved successfully.',
            'saved': saved,
            'updated_count': updated_count,
            'created_count': created_count,
        })
