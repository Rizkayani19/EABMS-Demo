from decimal import Decimal
from django.db.models import Sum
from core.models import (
    Account, FinancialYear, Budget, BudgetLine, Transaction,
    FutureBudget, FutureBudgetLine, FutureBudgetKnownChange,
)

ZERO = Decimal('0.00')


def _active_actuals(account, fy):
    return Transaction.objects.filter(
        account=account,
        financial_year=fy,
        direction=Transaction.Direction.OUTFLOW,
        status=Transaction.Status.ACTIVE,
    ).select_related('account_head', 'major_head', 'sub_head', 'unit', 'outflow_nature')


def _approved_budget_lines(account, fy):
    return BudgetLine.objects.filter(
        budget__account=account,
        budget__financial_year=fy,
        budget__status=Budget.Status.APPROVED,
    ).select_related('account_head', 'major_head', 'sub_head', 'unit', 'budget_type')


def build_existing_budget_analysis(account, fy, variance_threshold_pct=10):
    """Return budget-vs-actual analysis at Account Head + Unit grain.

    Actual historical transactions remain the SSOT. Budget is read only from the
    approved Budget/BudgetLine records. No historical transaction is modified.
    """
    rows = {}

    for line in _approved_budget_lines(account, fy):
        key = (line.account_head_id, line.unit_id)
        row = rows.setdefault(key, {
            'account_head_id': line.account_head_id,
            'account_head': line.account_head.name,
            'major_head': line.major_head.name if line.major_head else '',
            'sub_head': line.sub_head.name if line.sub_head else '',
            'unit_id': line.unit_id,
            'unit': line.unit.name if line.unit else 'All / Unattributed',
            'budget': ZERO,
            'actual': ZERO,
            'routine': ZERO,
            'continuing': ZERO,
            'additional': ZERO,
            'one_time': ZERO,
            'pass_through': ZERO,
        })
        row['budget'] += line.amount

    for tx in _active_actuals(account, fy):
        key = (tx.account_head_id, tx.unit_id)
        row = rows.setdefault(key, {
            'account_head_id': tx.account_head_id,
            'account_head': tx.account_head.name if tx.account_head else '',
            'major_head': tx.major_head.name if tx.major_head else '',
            'sub_head': tx.sub_head.name if tx.sub_head else '',
            'unit_id': tx.unit_id,
            'unit': tx.unit.name if tx.unit else 'All / Unattributed',
            'budget': ZERO,
            'actual': ZERO,
            'routine': ZERO,
            'continuing': ZERO,
            'additional': ZERO,
            'one_time': ZERO,
            'pass_through': ZERO,
        })
        row['actual'] += tx.amount
        if tx.pass_through:
            row['pass_through'] += tx.amount
        nature = (tx.outflow_nature.name if tx.outflow_nature else '').lower()
        if 'routine' in nature:
            row['routine'] += tx.amount
        elif 'continu' in nature:
            row['continuing'] += tx.amount
        elif 'add' in nature:
            row['additional'] += tx.amount
        elif 'one' in nature or 'exception' in nature:
            row['one_time'] += tx.amount

    result = []
    for row in rows.values():
        row['variance'] = row['actual'] - row['budget']
        row['utilisation_pct'] = (row['actual'] / row['budget'] * Decimal('100')) if row['budget'] else None
        row['significant_variance'] = bool(
            row['utilisation_pct'] is not None and abs(row['utilisation_pct'] - Decimal('100')) >= Decimal(str(variance_threshold_pct))
        )
        result.append(row)
    return sorted(result, key=lambda r: (r['account_head'], r['unit']))


def build_budget_driver_analysis(account, fy):
    """Summarise actual outflows by requirement nature for management review."""
    rows = build_existing_budget_analysis(account, fy, variance_threshold_pct=999999)
    totals = {
        'routine': ZERO, 'continuing': ZERO, 'additional': ZERO,
        'one_time': ZERO, 'pass_through': ZERO, 'actual': ZERO,
    }
    for row in rows:
        for key in totals:
            totals[key] += row[key]
    return totals


def create_future_budget_draft(account, source_fy, target_fy, personnel_revision_pct=Decimal('0.00'), routine_adjustment_pct=Decimal('0.00'), user=None):
    """Create/update a FutureBudget draft from the source FY.

    The generated amount is a management starting point, not an approved budget.
    Actuals and source budget remain unchanged.
    """
    if target_fy == source_fy:
        raise ValueError('Target Financial Year must differ from Source Financial Year.')
    if target_fy.start_date <= source_fy.end_date:
        raise ValueError('Target Financial Year must be after Source Financial Year.')

    future, _ = FutureBudget.objects.update_or_create(
        account=account,
        source_fy=source_fy,
        target_fy=target_fy,
        defaults={
            'status': FutureBudget.Status.DRAFT,
            'personnel_revision_pct': personnel_revision_pct,
            'routine_adjustment_pct': routine_adjustment_pct,
            'updated_by': user,
            'created_by': user,
        },
    )

    analysis = build_existing_budget_analysis(account, source_fy, variance_threshold_pct=999999)
    source_budget = {(line.account_head_id, line.unit_id): line.amount for line in _approved_budget_lines(account, source_fy)}

    for row in analysis:
        routine = row['routine'] * (Decimal('100') + routine_adjustment_pct) / Decimal('100')
        continuing = row['continuing']
        additional = row['additional']
        one_time = row['one_time']
        known = ZERO
        baseline = row['actual'] if row['actual'] else source_budget.get((row['account_head_id'], row['unit_id']), ZERO)
        suggested = max(baseline, routine + continuing + additional)

        # One-time/exceptional expenditure is retained as evidence but is not
        # automatically carried into the recurring projection.
        if one_time and suggested == ZERO:
            suggested = baseline - one_time if baseline > one_time else ZERO

        line, _ = FutureBudgetLine.objects.update_or_create(
            future_budget=future,
            account_head_id=row['account_head_id'],
            defaults={
                'major_head_id': next((r['major_head_id'] for r in analysis if r['account_head_id'] == row['account_head_id']), None),
                'sub_head_id': next((r['sub_head_id'] for r in analysis if r['account_head_id'] == row['account_head_id']), None),
                'previous_budget': source_budget.get((row['account_head_id'], row['unit_id']), ZERO),
                'previous_actual': row['actual'],
                'routine_amount': routine,
                'continuing_amount': continuing,
                'addl_amount': additional,
                'onetime_amount': one_time,
                'known_change_amount': known,
                'personnel_amount': ZERO,
                'system_suggested': suggested,
                'suggestion_breakdown': {
                    'source_budget': str(source_budget.get((row['account_head_id'], row['unit_id']), ZERO)),
                    'source_actual': str(row['actual']),
                    'routine': str(routine),
                    'continuing': str(continuing),
                    'additional': str(additional),
                    'one_time_excluded_from_recurring_projection': str(one_time),
                    'method': 'historical actual + classified continuing/additional requirements; one-time expenditure not automatically carried forward',
                },
                'routine_evidence': 'Derived from source FY transaction nature classification.',
                'is_routine': routine > ZERO,
                'is_addl': additional > ZERO,
                'is_onetime': one_time > ZERO,
                'continuing_flag': 'CONTINUING' if continuing > ZERO else '',
            },
        )

    return future


def apply_future_budget_known_changes(future_budget):
    """Recalculate system suggestions after explicit management known changes."""
    for line in future_budget.lines.all():
        known = future_budget.known_changes.filter(account_head=line.account_head).aggregate(total=Sum('amount'))['total'] or ZERO
        line.known_change_amount = known
        line.system_suggested = line.routine_amount + line.continuing_amount + line.addl_amount + known + line.personnel_amount
        line.save(update_fields=['known_change_amount', 'system_suggested', 'updated_at'])
    return future_budget


def future_budget_summary(future_budget):
    lines = future_budget.lines.all()
    system = lines.aggregate(total=Sum('system_suggested'))['total'] or ZERO
    proposed = lines.aggregate(total=Sum('user_proposed'))['total'] or ZERO
    approved = lines.aggregate(total=Sum('approved_amount'))['total'] or ZERO
    return {
        'account': future_budget.account.name,
        'source_fy': future_budget.source_fy.name,
        'target_fy': future_budget.target_fy.name,
        'status': future_budget.status,
        'system_suggested': system,
        'management_proposed': proposed,
        'approved': approved,
        'line_count': lines.count(),
    }
