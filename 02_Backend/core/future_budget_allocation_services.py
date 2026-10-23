from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Sum

from core.models import FutureBudgetLine, Transaction, Unit, InternalSection
from core.future_budget_allocation_models import FutureBudgetAllocation

ZERO = Decimal('0.00')


def get_parent_target(line):
    """Return the amount that organisational allocations must reconcile to."""
    if line.approved_amount is not None:
        return line.approved_amount
    if line.user_proposed is not None:
        return line.user_proposed
    return line.system_suggested


def allocation_total(line):
    return line.allocations.aggregate(total=Sum('allocated_amount'))['total'] or ZERO


def allocation_reconciliation(line):
    target = get_parent_target(line)
    allocated = allocation_total(line)
    return {'target': target, 'allocated': allocated, 'difference': allocated - target, 'is_reconciled': allocated == target}


def validate_allocations(line):
    result = allocation_reconciliation(line)
    if not result['is_reconciled']:
        raise ValidationError(
            f"Future budget allocation does not reconcile for {line.account_head}: "
            f"target Rs {result['target']:,.2f}, allocated Rs {result['allocated']:,.2f}, "
            f"difference Rs {result['difference']:,.2f}."
        )
    return result


def save_allocation(*, line, amount, unit=None, internal_section=None, user=None, justification='', remarks=''):
    """Create/update one monetary organisational allocation and return its reconciliation."""
    amount = Decimal(str(amount)).quantize(Decimal('0.01'))
    if amount <= ZERO:
        raise ValidationError('Allocation amount must be greater than zero.')
    allocation, _ = FutureBudgetAllocation.objects.update_or_create(
        future_budget_line=line,
        unit=unit,
        internal_section=internal_section,
        defaults={'allocated_amount': amount, 'justification': justification, 'remarks': remarks,
                  'updated_by': user, 'created_by': user},
    )
    return allocation, allocation_reconciliation(line)


def delete_allocation(*, allocation):
    line = allocation.future_budget_line
    allocation.delete()
    return allocation_reconciliation(line)


def _money(value):
    return Decimal(str(value or 0)).quantize(Decimal('0.01'))


def _pct_change(current, previous):
    current, previous = _money(current), _money(previous)
    if previous == ZERO:
        return None if current == ZERO else Decimal('100.00')
    return ((current - previous) / previous * Decimal('100')).quantize(Decimal('0.01'))


def build_future_organisational_analysis(future_budget, units=None, internal_sections=None):
    """Build filtered management analysis of future budget by Unit and Section.

    Future amounts come only from FutureBudgetAllocation. Previous actuals come
    directly from Transaction, the financial SSOT. Unit and Section are independent
    dimensions: a Unit normally has a responsible Section, but it is not mandatory;
    one Unit may have multiple managing Sections and an allocation may involve
    multiple Units and/or Sections.
    """
    account = future_budget.account
    source_fy = future_budget.source_fy
    unit_filter = {v for v in (units or []) if v}
    section_filter = {v for v in (internal_sections or []) if v}

    allocations = FutureBudgetAllocation.objects.filter(
        future_budget_line__future_budget=future_budget
    ).select_related('future_budget_line__account_head', 'unit', 'internal_section')
    if unit_filter:
        allocations = allocations.filter(unit__name__in=unit_filter)
    if section_filter:
        allocations = allocations.filter(internal_section__name__in=section_filter)

    unit_totals, section_totals, matrix_totals = {}, {}, {}
    head_unit_totals, head_section_totals = {}, {}
    for a in allocations.iterator():
        amount = _money(a.allocated_amount)
        unit_name = a.unit.name if a.unit else 'Unallocated / General'
        section_name = a.internal_section.name if a.internal_section else 'Unallocated / General'
        head_name = a.future_budget_line.account_head.name
        unit_totals[unit_name] = unit_totals.get(unit_name, ZERO) + amount
        section_totals[section_name] = section_totals.get(section_name, ZERO) + amount
        matrix_totals[(unit_name, section_name)] = matrix_totals.get((unit_name, section_name), ZERO) + amount
        head_unit_totals[(head_name, unit_name)] = head_unit_totals.get((head_name, unit_name), ZERO) + amount
        head_section_totals[(head_name, section_name)] = head_section_totals.get((head_name, section_name), ZERO) + amount

    txns = Transaction.objects.filter(account=account, financial_year=source_fy,
                                      direction='OUTFLOW', status='ACTIVE')
    if unit_filter:
        txns = txns.filter(unit__name__in=unit_filter)
    if section_filter:
        txns = txns.filter(internal_section__name__in=section_filter)

    unit_actuals = {}
    for row in txns.values('unit__name').annotate(total=Sum('amount')):
        unit_actuals[row['unit__name'] or 'Unattributed'] = _money(row['total'])
    section_actuals = {}
    for row in txns.values('internal_section__name').annotate(total=Sum('amount')):
        section_actuals[row['internal_section__name'] or 'Unattributed'] = _money(row['total'])

    # Only include configured Masters when no filter is active, so filtered reports
    # remain focused while unfiltered management reports retain the complete Master list.
    if not unit_filter:
        for unit in Unit.objects.filter(is_active=True).order_by('display_order', 'name'):
            unit_totals.setdefault(unit.name, ZERO)
            unit_actuals.setdefault(unit.name, ZERO)
    if not section_filter:
        for section in InternalSection.objects.filter(is_active=True).order_by('display_order', 'name'):
            section_totals.setdefault(section.name, ZERO)
            section_actuals.setdefault(section.name, ZERO)

    unit_rows = []
    for name in sorted(unit_totals):
        future_amount, previous = _money(unit_totals[name]), _money(unit_actuals.get(name, ZERO))
        unit_rows.append({'unit': name, 'previous_actual': previous, 'future_allocated': future_amount,
                          'difference': future_amount - previous, 'change_pct': _pct_change(future_amount, previous)})

    section_rows = []
    for name in sorted(section_totals):
        future_amount, previous = _money(section_totals[name]), _money(section_actuals.get(name, ZERO))
        section_rows.append({'internal_section': name, 'previous_actual': previous, 'future_allocated': future_amount,
                             'difference': future_amount - previous, 'change_pct': _pct_change(future_amount, previous)})

    matrix_rows = [{'unit': k[0], 'internal_section': k[1], 'future_allocated': _money(v)}
                   for k, v in sorted(matrix_totals.items())]
    head_unit_rows = [{'account_head': k[0], 'unit': k[1], 'future_allocated': _money(v)}
                      for k, v in sorted(head_unit_totals.items())]
    head_section_rows = [{'account_head': k[0], 'internal_section': k[1], 'future_allocated': _money(v)}
                         for k, v in sorted(head_section_totals.items())]

    line_reconciliation = []
    for line in future_budget.lines.select_related('account_head').prefetch_related('allocations'):
        rec = allocation_reconciliation(line)
        line_reconciliation.append({'account_head': line.account_head.name, 'target': _money(rec['target']),
                                    'allocated': _money(rec['allocated']), 'difference': _money(rec['difference']),
                                    'is_reconciled': rec['is_reconciled']})

    return {
        'unit_rows': unit_rows, 'section_rows': section_rows, 'matrix_rows': matrix_rows,
        'head_unit_rows': head_unit_rows, 'head_section_rows': head_section_rows,
        'line_reconciliation': line_reconciliation,
        'future_allocation_total': sum(unit_totals.values(), ZERO),
        'previous_unit_actual_total': sum(unit_actuals.values(), ZERO),
        'previous_section_actual_total': sum(section_actuals.values(), ZERO),
        'reconciled_lines': sum(1 for r in line_reconciliation if r['is_reconciled']),
        'unreconciled_lines': sum(1 for r in line_reconciliation if not r['is_reconciled']),
        'filters': {'units': sorted(unit_filter), 'internal_sections': sorted(section_filter)},
    }
