from datetime import date, datetime
from decimal import Decimal
from django.db.models import Sum
from core.models import Budget, BudgetLine, Transaction, FutureBudget, FutureBudgetLine
ZERO = Decimal('0.00')

def _coerce_date(value):
    if isinstance(value, datetime): return value.date()
    if isinstance(value, date): return value
    if isinstance(value, str):
        try: return date.fromisoformat(value)
        except ValueError: pass
    return value

def _actuals(account, fy):
    return Transaction.objects.filter(account=account, financial_year=fy, direction=Transaction.Direction.OUTFLOW, status=Transaction.Status.ACTIVE).select_related('account_head', 'major_head', 'sub_head', 'unit', 'outflow_nature')

def _approved_budget(account, fy):
    return BudgetLine.objects.filter(budget__account=account, budget__financial_year=fy, budget__status=Budget.Status.APPROVED).select_related('account_head', 'major_head', 'sub_head', 'unit', 'budget_type')

def existing_budget_analysis(account, fy, variance_threshold_pct=10):
    rows = {}
    def blank(key, ah, mh=None, sh=None, unit=None):
        return rows.setdefault(key, {'account_head_id': ah, 'account_head': getattr(ah, 'name', ''), 'major_head': getattr(mh, 'name', '') if mh else '', 'sub_head': getattr(sh, 'name', '') if sh else '', 'unit_id': getattr(unit, 'id', None) if unit else None, 'unit': getattr(unit, 'name', 'All / Unattributed') if unit else 'All / Unattributed', 'budget': ZERO, 'actual': ZERO, 'routine': ZERO, 'continuing': ZERO, 'additional': ZERO, 'one_time': ZERO, 'pass_through': ZERO})
    for line in _approved_budget(account, fy):
        key = (line.account_head_id, line.unit_id); blank(key, line.account_head, line.major_head, line.sub_head, line.unit)['budget'] += line.amount
    for tx in _actuals(account, fy):
        key = (tx.account_head_id, tx.unit_id); row = blank(key, tx.account_head, tx.major_head, tx.sub_head, tx.unit); row['actual'] += tx.amount
        if tx.pass_through: row['pass_through'] += tx.amount
        nature = (tx.outflow_nature.name if tx.outflow_nature else '').lower()
        if 'routine' in nature: row['routine'] += tx.amount
        elif 'continu' in nature: row['continuing'] += tx.amount
        elif 'add' in nature: row['additional'] += tx.amount
        elif 'one' in nature or 'exception' in nature: row['one_time'] += tx.amount
    result = []
    for row in rows.values():
        row['variance'] = row['actual'] - row['budget']; row['utilisation_pct'] = (row['actual'] / row['budget'] * Decimal('100')) if row['budget'] else None
        row['significant_variance'] = bool(row['utilisation_pct'] is not None and abs(row['utilisation_pct'] - Decimal('100')) >= Decimal(str(variance_threshold_pct))); result.append(row)
    return sorted(result, key=lambda r: (r['account_head'], r['unit']))

def budget_driver_analysis(account, fy):
    totals = {k: ZERO for k in ('actual', 'routine', 'continuing', 'additional', 'one_time', 'pass_through')}
    for row in existing_budget_analysis(account, fy, 999999):
        for key in totals: totals[key] += row[key]
    return totals

def _head_baselines(rows):
    grouped = {}
    for row in rows:
        key = row['account_head_id']; g = grouped.setdefault(key, {'account_head_id': key, 'major_head': row['major_head'], 'sub_head': row['sub_head'], 'previous_budget': ZERO, 'previous_actual': ZERO, 'routine': ZERO, 'continuing': ZERO, 'additional': ZERO, 'one_time': ZERO})
        g['previous_budget'] += row['budget']; g['previous_actual'] += row['actual']; g['routine'] += row['routine']; g['continuing'] += row['continuing']; g['additional'] += row['additional']; g['one_time'] += row['one_time']
    return grouped.values()

def create_future_budget_draft(account, source_fy, target_fy, personnel_revision_pct=ZERO, routine_adjustment_pct=ZERO, user=None):
    if target_fy == source_fy or _coerce_date(target_fy.start_date) <= _coerce_date(source_fy.end_date): raise ValueError('Target Financial Year must be after Source Financial Year.')
    future, _ = FutureBudget.objects.update_or_create(account=account, source_fy=source_fy, target_fy=target_fy, defaults={'status': FutureBudget.Status.DRAFT, 'personnel_revision_pct': personnel_revision_pct, 'routine_adjustment_pct': routine_adjustment_pct, 'updated_by': user, 'created_by': user})
    for row in _head_baselines(existing_budget_analysis(account, source_fy, 999999)):
        routine = row['routine'] * (Decimal('100') + routine_adjustment_pct) / Decimal('100'); recurring = routine + row['continuing'] + row['additional']; baseline = row['previous_actual'] or row['previous_budget']; suggested = max(baseline - row['one_time'], ZERO, recurring)
        account_head_id = row['account_head_id'].id if hasattr(row['account_head_id'], 'id') else row['account_head_id']
        FutureBudgetLine.objects.update_or_create(future_budget=future, account_head_id=account_head_id, defaults={'previous_budget': row['previous_budget'], 'previous_actual': row['previous_actual'], 'routine_amount': routine, 'continuing_amount': row['continuing'], 'addl_amount': row['additional'], 'onetime_amount': row['one_time'], 'known_change_amount': ZERO, 'personnel_amount': ZERO, 'system_suggested': suggested, 'suggestion_breakdown': {'source_budget': str(row['previous_budget']), 'source_actual': str(row['previous_actual']), 'routine': str(routine), 'continuing': str(row['continuing']), 'additional': str(row['additional']), 'one_time_excluded_from_recurring_projection': str(row['one_time']), 'unit_grain_aggregated': True}, 'routine_evidence': 'Derived from source FY transaction nature classification.', 'is_routine': routine > ZERO, 'is_addl': row['additional'] > ZERO, 'is_onetime': row['one_time'] > ZERO, 'continuing_flag': 'CONTINUING' if row['continuing'] > ZERO else ''})
    return future

def apply_known_changes(future_budget):
    for line in future_budget.lines.all():
        known = future_budget.known_changes.filter(account_head=line.account_head).aggregate(total=Sum('amount'))['total'] or ZERO; line.known_change_amount = known; line.system_suggested = line.routine_amount + line.continuing_amount + line.addl_amount + known + line.personnel_amount; line.save(update_fields=['known_change_amount', 'system_suggested', 'updated_at'])
    return future_budget

def future_budget_summary(future_budget):
    lines = future_budget.lines.all(); return {'account': future_budget.account.name, 'source_fy': future_budget.source_fy.name, 'target_fy': future_budget.target_fy.name, 'status': future_budget.status, 'system_suggested': lines.aggregate(v=Sum('system_suggested'))['v'] or ZERO, 'management_proposed': lines.aggregate(v=Sum('user_proposed'))['v'] or ZERO, 'approved': lines.aggregate(v=Sum('approved_amount'))['v'] or ZERO, 'line_count': lines.count()}
