from decimal import Decimal
from django.db.models import Sum
from core.models import Transaction


def _active_transactions(filters):
    qs = Transaction.objects.filter(status=Transaction.Status.ACTIVE)
    if filters.get('account'): qs = qs.filter(account=filters['account'])
    if filters.get('financial_year'): qs = qs.filter(financial_year=filters['financial_year'])
    if filters.get('start_date'): qs = qs.filter(transaction_date__gte=filters['start_date'])
    if filters.get('end_date'): qs = qs.filter(transaction_date__lte=filters['end_date'])
    if filters.get('direction'): qs = qs.filter(direction=filters['direction'])
    if filters.get('account_head'): qs = qs.filter(account_head=filters['account_head'])
    if filters.get('sub_head'): qs = qs.filter(sub_head=filters['sub_head'])
    if filters.get('major_head'): qs = qs.filter(major_head=filters['major_head'])
    if filters.get('outflow_nature'): qs = qs.filter(outflow_nature=filters['outflow_nature'])
    if filters.get('unit_ids'): qs = qs.filter(transaction_units__id__in=filters['unit_ids'])
    if filters.get('internal_section_ids'): qs = qs.filter(transaction_sections__id__in=filters['internal_section_ids'])
    return qs.distinct()


def _allocation_rows(filters):
    qs = _active_transactions(filters).prefetch_related('transaction_units', 'transaction_sections').order_by('transaction_date', 'id')
    rows = []
    for tx in qs:
        units = list(tx.transaction_units.all()) or ([tx.unit] if tx.unit else [None])
        sections = list(tx.transaction_sections.all()) or ([tx.internal_section] if tx.internal_section else [None])
        # Reporting grain is the explicit combination. A transaction with multiple units and sections
        # is represented at combination grain; the transaction amount remains available separately.
        for unit in units:
            for section in sections:
                rows.append({'transaction_id': tx.transaction_number, 'date': tx.transaction_date, 'direction': tx.direction,
                             'account': tx.account.name, 'account_head': tx.account_head.name if tx.account_head else '',
                             'sub_head': tx.sub_head.name if tx.sub_head else '', 'unit': unit.name if unit else '',
                             'internal_section': section.name if section else '', 'amount': tx.amount,
                             'transaction_amount': tx.amount})
    return rows


def build_unit_summary(filters):
    qs = _active_transactions(filters)
    rows = qs.values('transaction_units__id', 'transaction_units__name').annotate(total=Sum('amount'))
    return sorted([{'unit': r['transaction_units__name'] or 'Unspecified Unit', 'amount': r['total'] or Decimal('0.00')} for r in rows], key=lambda x: x['unit'])


def build_internal_section_summary(filters):
    qs = _active_transactions(filters)
    rows = qs.values('transaction_sections__id', 'transaction_sections__name').annotate(total=Sum('amount'))
    return sorted([{'internal_section': r['transaction_sections__name'] or 'Unspecified Section', 'amount': r['total'] or Decimal('0.00')} for r in rows], key=lambda x: x['internal_section'])


def build_unit_section_summary(filters):
    data = {}
    for row in _allocation_rows(filters):
        key = (row['unit'], row['internal_section'])
        data[key] = data.get(key, Decimal('0.00')) + row['amount']
    return [{'unit': k[0] or 'Unspecified Unit', 'internal_section': k[1] or 'Unspecified Section', 'amount': v} for k, v in sorted(data.items())]


def build_organisational_transactions(filters):
    return _allocation_rows(filters)
