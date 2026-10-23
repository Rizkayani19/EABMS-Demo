from decimal import Decimal
from django.db.models import Sum
from core.models import (
    Transaction, BudgetLine, AccountHead, FutureBudgetLine,
    FutureBudgetKnownChange, FutureBudgetPersonnel, FutureBudget,
)
from core.future_budget_management_models import FutureBudgetManagementInput
from core.future_budget_calculation import calculate_future_budget_components

ZERO = Decimal('0.00')
HUNDRED = Decimal('100')


def money(value):
    return (value or ZERO).quantize(Decimal('0.01'))


def analyze_account_head(account, source_fy, account_head):
    """Analyse one head using ACTIVE source-FY transactions only.

    Historical analysis retains all active outflows. Planning calculations use
    the non-pass-through subset so internal/pass-through movements do not become
    recurring expenditure in the future-budget baseline.
    """
    txns = Transaction.objects.filter(
        account=account,
        financial_year=source_fy,
        account_head=account_head,
        direction=Transaction.Direction.OUTFLOW,
        status=Transaction.Status.ACTIVE,
    )
    previous_actual = money(txns.aggregate(total=Sum('amount'))['total'])
    planning_txns = txns.filter(pass_through=False)
    planning_actual = money(planning_txns.aggregate(total=Sum('amount'))['total'])

    months_with_activity = {
        f"{r.transaction_date.year}-{r.transaction_date.month:02d}"
        for r in planning_txns.only('transaction_date')
        if r.transaction_date
    }
    month_count = len(months_with_activity)
    is_salary = 'salar' in account_head.name.lower()
    is_routine = month_count >= 8 or is_salary
    is_onetime = month_count == 1 and planning_actual > ZERO and not is_salary
    addl_amount = money(
        planning_txns.filter(
            outflow_nature__name__icontains='addl'
        ).aggregate(total=Sum('amount'))['total']
    )
    pass_through_amount = money(
        txns.filter(pass_through=True).aggregate(total=Sum('amount'))['total']
    )
    nature_breakdown = {}
    for row in planning_txns.exclude(outflow_nature__isnull=True).values('outflow_nature__name').annotate(total=Sum('amount')):
        nature_breakdown[row['outflow_nature__name']] = money(row['total'])
    return {
        'previous_actual': previous_actual,
        'planning_actual': planning_actual,
        'month_count': month_count,
        'is_routine': is_routine,
        'is_addl': addl_amount > ZERO,
        'is_onetime': is_onetime,
        'addl_amount': addl_amount,
        'pass_through_amount': pass_through_amount,
        'nature_breakdown': nature_breakdown,
        'routine_evidence': (
            f'Recurring in {month_count} of 12 months in source FY; '
            f'planning actual excluding pass-through Rs {planning_actual:,.2f}; '
            f'additional-tagged actual Rs {addl_amount:,.2f}; '
            f'pass-through actual Rs {pass_through_amount:,.2f}'
        ),
        'continuing_flag': 'needs_more_history' if planning_actual > ZERO else '',
    }


def analyze_major_head(account, source_fy, major_head):
    """Analyse one Sub-Fund (MajorHead) using ACTIVE source-FY transactions only."""
    txns = Transaction.objects.filter(
        account=account,
        financial_year=source_fy,
        major_head=major_head,
        direction=Transaction.Direction.OUTFLOW,
        status=Transaction.Status.ACTIVE,
    )
    previous_actual = money(txns.aggregate(total=Sum('amount'))['total'])
    planning_txns = txns.filter(pass_through=False)
    planning_actual = money(planning_txns.aggregate(total=Sum('amount'))['total'])

    months_with_activity = {
        f"{r.transaction_date.year}-{r.transaction_date.month:02d}"
        for r in planning_txns.only('transaction_date')
        if r.transaction_date
    }
    month_count = len(months_with_activity)
    is_routine = month_count >= 8
    is_onetime = month_count == 1 and planning_actual > ZERO
    addl_amount = money(
        planning_txns.filter(
            outflow_nature__name__icontains='addl'
        ).aggregate(total=Sum('amount'))['total']
    )
    pass_through_amount = money(
        txns.filter(pass_through=True).aggregate(total=Sum('amount'))['total']
    )
    nature_breakdown = {}
    for row in planning_txns.exclude(outflow_nature__isnull=True).values('outflow_nature__name').annotate(total=Sum('amount')):
        nature_breakdown[row['outflow_nature__name']] = money(row['total'])
    return {
        'previous_actual': previous_actual,
        'planning_actual': planning_actual,
        'month_count': month_count,
        'is_routine': is_routine,
        'is_addl': addl_amount > ZERO,
        'is_onetime': is_onetime,
        'addl_amount': addl_amount,
        'pass_through_amount': pass_through_amount,
        'nature_breakdown': nature_breakdown,
        'routine_evidence': (
            f'Recurring in {month_count} of 12 months in source FY; '
            f'planning actual excluding pass-through Rs {planning_actual:,.2f}; '
            f'additional-tagged actual Rs {addl_amount:,.2f}; '
            f'pass-through actual Rs {pass_through_amount:,.2f}'
        ),
        'continuing_flag': 'needs_more_history' if planning_actual > ZERO else '',
    }


def compute_system_suggested(
    previous_actual, routine_adj_pct, continuing_amount,
    known_change_amount, personnel_amount, onetime_amount,
    additional_management_amount=ZERO
):
    """Backward-compatible facade over the canonical Future Budget calculator."""
    result = calculate_future_budget_components(
        previous_actual=previous_actual,
        routine_adj_pct=routine_adj_pct,
        continuing_amount=continuing_amount,
        known_change_amount=known_change_amount,
        personnel_amount=personnel_amount,
        onetime_amount=onetime_amount,
        additional_management_amount=additional_management_amount,
    )
    return result.system_suggested, result.breakdown


def _management_input_amounts(future_budget, account_head):
    rows = FutureBudgetManagementInput.objects.filter(
        future_budget=future_budget,
        account_head=account_head,
        status=FutureBudgetManagementInput.Status.ACTIVE,
    )
    continuing = ZERO
    additional = ZERO
    other = ZERO
    detail = []
    for row in rows.iterator():
        amount = money(row.amount)
        if row.input_type == FutureBudgetManagementInput.InputType.CONTINUING:
            continuing += amount
        elif row.input_type == FutureBudgetManagementInput.InputType.ADDITIONAL:
            additional += amount
        else:
            other += amount
        detail.append({
            'id': row.id,
            'type': row.input_type,
            'description': row.description,
            'amount': str(amount),
            'units': list(row.units.values_list('name', flat=True)),
            'internal_sections': list(
                row.internal_sections.values_list('name', flat=True)
            ),
            'reference': row.reference,
        })
    return continuing, additional, other, detail


def _known_change_amounts(future_budget, account_head):
    rows = FutureBudgetKnownChange.objects.filter(
        future_budget=future_budget,
        account_head=account_head
    )
    positive = ZERO
    discontinued = ZERO
    for row in rows.iterator():
        amount = money(row.amount)
        if row.change_type == FutureBudgetKnownChange.ChangeType.DISCONTINUED:
            discontinued += amount
        else:
            positive += amount
    return positive - discontinued, positive, discontinued


def _personnel_effect_for_head(future_budget, account_head):
    if 'salar' not in account_head.name.lower():
        return ZERO
    projected = (
        FutureBudgetPersonnel.objects
        .filter(future_budget=future_budget)
        .aggregate(total=Sum('projected_cost'))['total'] or ZERO
    )
    current = (
        FutureBudgetPersonnel.objects
        .filter(future_budget=future_budget)
        .aggregate(total=Sum('current_annual_cost'))['total'] or ZERO
    )
    return money(projected - current)


def build_future_budget_lines(future_budget, allow_approved=False):
    """Build planning lines from non-pass-through historical actuals.

    An already approved Future Budget is immutable through this planning path,
    unless explicitly allowed during synchronization or administrative operations.
    """
    account = future_budget.account
    source_fy = future_budget.source_fy
    if not allow_approved and future_budget.status == FutureBudget.Status.APPROVED:
        raise ValueError(
            f'Future Budget #{future_budget.pk} is already APPROVED; '
            'analytical planning cannot overwrite an approved budget.'
        )

    routine_adj_pct = money(future_budget.routine_adjustment_pct)

    from .models import MajorHead
    if getattr(future_budget, 'budget_allocation_basis', 'ACCOUNT_HEAD') == 'SUB_FUND':
        # Sub-Fund allocation basis
        sub_funds = MajorHead.objects.filter(account=account, is_active=True).order_by('display_order', 'name')
        for sf in sub_funds:
            analysis = analyze_major_head(account, source_fy, sf)
            previous_budget = money(
                BudgetLine.objects.filter(
                    budget__account=account,
                    budget__financial_year=source_fy,
                    major_head=sf,
                ).aggregate(total=Sum('amount'))['total']
            )
            onetime_amount = analysis['planning_actual'] if analysis['is_onetime'] else ZERO
            baseline = ZERO if analysis['is_onetime'] else analysis['planning_actual']
            calculation = calculate_future_budget_components(
                previous_actual=baseline,
                routine_adj_pct=routine_adj_pct,
                continuing_amount=ZERO,
                known_change_amount=ZERO,
                personnel_amount=ZERO,
                onetime_amount=ZERO,
                additional_management_amount=ZERO,
            )
            inflow_actual = money(
                Transaction.objects.filter(
                    account=account,
                    financial_year=source_fy,
                    direction=Transaction.Direction.INFLOW,
                    status=Transaction.Status.ACTIVE,
                    major_head=sf,
                ).aggregate(total=Sum('amount'))['total']
            )
            from .budget_inflow_models import BudgetInflowLine
            inflow_budget = money(
                BudgetInflowLine.objects.filter(
                    budget__account=account,
                    budget__financial_year=source_fy,
                    major_head=sf,
                ).aggregate(total=Sum('amount'))['total']
            )
            suggested_inflow = inflow_actual if inflow_actual > ZERO else inflow_budget

            suggested = calculation.system_suggested
            breakdown = calculation.breakdown
            breakdown.update({
                'historical_actual_including_pass_through': str(analysis['previous_actual']),
                'planning_actual_excluding_pass_through': str(analysis['planning_actual']),
                'additional_actual': str(analysis['addl_amount']),
                'pass_through_actual': str(analysis['pass_through_amount']),
                'historical_onetime_excluded': str(onetime_amount),
                'previous_inflow_actual': str(inflow_actual),
                'previous_inflow_budget': str(inflow_budget),
                'suggested_inflow': str(suggested_inflow),
            })
            line_obj, _ = FutureBudgetLine.objects.update_or_create(
                future_budget=future_budget,
                major_head=sf,
                account_head=None,
                defaults={
                    'previous_budget': previous_budget,
                    'previous_actual': analysis['previous_actual'],
                    'routine_amount': analysis['planning_actual'] if analysis['is_routine'] else ZERO,
                    'continuing_amount': ZERO,
                    'addl_amount': analysis['addl_amount'],
                    'onetime_amount': onetime_amount,
                    'known_change_amount': ZERO,
                    'personnel_amount': ZERO,
                    'system_suggested': suggested,
                    'suggestion_breakdown': breakdown,
                    'routine_evidence': analysis['routine_evidence'],
                    'is_routine': analysis['is_routine'],
                    'is_addl': analysis['is_addl'],
                    'is_onetime': analysis['is_onetime'],
                    'continuing_flag': analysis['continuing_flag'],
                },
            )
            from .future_budget_inflow_proposal import get_user_proposed_inflow, set_user_proposed_inflow
            if get_user_proposed_inflow(line_obj) is None:
                set_user_proposed_inflow(line_obj, suggested_inflow)
                line_obj.save(update_fields=['suggestion_breakdown'])
        return future_budget

    active_heads = (
        Transaction.objects.filter(
            account=account,
            financial_year=source_fy,
            direction=Transaction.Direction.OUTFLOW,
            status=Transaction.Status.ACTIVE,
            pass_through=False,
        )
        .values_list('account_head', flat=True)
        .distinct()
    )
    inflow_heads = (
        Transaction.objects.filter(
            account=account,
            financial_year=source_fy,
            direction=Transaction.Direction.INFLOW,
            status=Transaction.Status.ACTIVE,
        )
        .values_list('account_head', flat=True)
        .distinct()
    )
    input_heads = (
        FutureBudgetManagementInput.objects
        .filter(
            future_budget=future_budget,
            status=FutureBudgetManagementInput.Status.ACTIVE
        )
        .values_list('account_head', flat=True)
        .distinct()
    )
    master_heads = (
        AccountHead.objects.filter(
            account=account,
            is_active=True,
        )
        .values_list('id', flat=True)
    )

    all_head_ids = set(active_heads) | set(input_heads) | set(inflow_heads) | set(master_heads)
    for ah_id in all_head_ids:
        ah = AccountHead.objects.get(pk=ah_id)
        analysis = analyze_account_head(account, source_fy, ah)
        previous_budget = money(
            BudgetLine.objects.filter(
                budget__account=account,
                budget__financial_year=source_fy,
                account_head=ah,
            ).aggregate(total=Sum('amount'))['total']
        )
        known_change, known_positive, known_discontinued = _known_change_amounts(
            future_budget, ah
        )
        personnel_effect = _personnel_effect_for_head(future_budget, ah)
        (
            management_continuing,
            management_additional,
            management_other,
            management_detail,
        ) = _management_input_amounts(future_budget, ah)

        onetime_amount = analysis['planning_actual'] if analysis['is_onetime'] else ZERO

        # Planning baseline excludes pass-through and one-time historical expenditure.
        # Salary heads are personnel-driven and do not receive generic routine uplift.
        baseline = ZERO if analysis['is_onetime'] else analysis['planning_actual']
        effective_routine_pct = ZERO if ('salar' in ah.name.lower()) else routine_adj_pct
        calculation = calculate_future_budget_components(
            previous_actual=baseline,
            routine_adj_pct=effective_routine_pct,
            continuing_amount=management_continuing,
            known_change_amount=known_change,
            personnel_amount=personnel_effect,
            onetime_amount=ZERO,
            additional_management_amount=management_additional,
        )
        inflow_actual = money(
            Transaction.objects.filter(
                account=account,
                financial_year=source_fy,
                direction=Transaction.Direction.INFLOW,
                status=Transaction.Status.ACTIVE,
                account_head=ah,
            ).aggregate(total=Sum('amount'))['total']
        )
        from .budget_inflow_models import BudgetInflowLine
        inflow_budget = money(
            BudgetInflowLine.objects.filter(
                budget__account=account,
                budget__financial_year=source_fy,
                account_head=ah,
            ).aggregate(total=Sum('amount'))['total']
        )
        suggested_inflow = inflow_actual if inflow_actual > ZERO else inflow_budget

        suggested = calculation.system_suggested
        breakdown = calculation.breakdown
        breakdown.update({
            'historical_actual_including_pass_through': str(analysis['previous_actual']),
            'planning_actual_excluding_pass_through': str(analysis['planning_actual']),
            'additional_actual': str(analysis['addl_amount']),
            'pass_through_actual': str(analysis['pass_through_amount']),
            'management_other_input': str(management_other),
            'known_change_positive': str(known_positive),
            'known_change_discontinued': str(known_discontinued),
            'historical_onetime_excluded': str(onetime_amount),
            'management_input_detail': management_detail,
            'previous_inflow_actual': str(inflow_actual),
            'previous_inflow_budget': str(inflow_budget),
            'suggested_inflow': str(suggested_inflow),
        })
        line_obj, _ = FutureBudgetLine.objects.update_or_create(
            future_budget=future_budget,
            account_head=ah,
            defaults={
                'major_head': ah.major_head,
                'sub_head': ah.sub_head,
                'previous_budget': previous_budget,
                'previous_actual': analysis['previous_actual'],
                'routine_amount': (
                    analysis['planning_actual']
                    if (analysis['is_routine'] and 'salar' not in ah.name.lower())
                    else ZERO
                ),
                'continuing_amount': management_continuing,
                'addl_amount': analysis['addl_amount'],
                'onetime_amount': onetime_amount,
                'known_change_amount': known_change,
                'personnel_amount': personnel_effect,
                'system_suggested': ZERO if ah.head_type == AccountHead.HeadType.INFLOW else suggested,
                'suggestion_breakdown': breakdown,
                'routine_evidence': analysis['routine_evidence'],
                'is_routine': analysis['is_routine'],
                'is_addl': analysis['is_addl'],
                'is_onetime': analysis['is_onetime'],
                'continuing_flag': analysis['continuing_flag'],
            },
        )
        from .future_budget_inflow_proposal import get_user_proposed_inflow, set_user_proposed_inflow
        if get_user_proposed_inflow(line_obj) is None and (ah.head_type in ('INFLOW', 'BOTH') or inflow_actual > ZERO):
            set_user_proposed_inflow(line_obj, suggested_inflow)
            line_obj.save(update_fields=['suggestion_breakdown'])
    return future_budget


def get_salaries_baseline(account, source_fy):
    salaries_heads = AccountHead.objects.filter(account=account, name__icontains='salar')
    return money(
        Transaction.objects.filter(
            account=account,
            financial_year=source_fy,
            account_head__in=salaries_heads,
            direction=Transaction.Direction.OUTFLOW,
            status=Transaction.Status.ACTIVE,
            pass_through=False,
        ).aggregate(total=Sum('amount'))['total']
    )


def get_future_budget_summary(future_budget):
    from .future_budget_inflow_proposal import get_user_proposed_inflow
    lines = future_budget.lines.select_related('account_head').all()
    agg = lines.aggregate(
        prev_budget=Sum('previous_budget'),
        prev_actual=Sum('previous_actual'),
        routine=Sum('routine_amount'),
        continuing=Sum('continuing_amount'),
        addl=Sum('addl_amount'),
        onetime=Sum('onetime_amount'),
        known_changes=Sum('known_change_amount'),
        personnel=Sum('personnel_amount'),
        system_suggested=Sum('system_suggested'),
        user_proposed=Sum('user_proposed'),
        approved=Sum('approved_amount'),
    )
    management_inputs = FutureBudgetManagementInput.objects.filter(
        future_budget=future_budget,
        status=FutureBudgetManagementInput.Status.ACTIVE
    )
    management_additional = money(
        management_inputs.filter(
            input_type=FutureBudgetManagementInput.InputType.ADDITIONAL
        ).aggregate(total=Sum('amount'))['total']
    )
    management_continuing = money(
        management_inputs.filter(
            input_type=FutureBudgetManagementInput.InputType.CONTINUING
        ).aggregate(total=Sum('amount'))['total']
    )
    management_other = money(
        management_inputs.filter(
            input_type=FutureBudgetManagementInput.InputType.OTHER
        ).aggregate(total=Sum('amount'))['total']
    )

    inflow_prev_budget = ZERO
    inflow_prev_actual = ZERO
    inflow_suggested = ZERO
    inflow_proposed = ZERO
    inflow_approved = ZERO
    for line in lines:
        bd = line.suggestion_breakdown or {}
        inflow_prev_budget += money(Decimal(str(bd.get('previous_inflow_budget') or '0.00')))
        inflow_prev_actual += money(Decimal(str(bd.get('previous_inflow_actual') or '0.00')))
        inflow_suggested += money(Decimal(str(bd.get('suggested_inflow') or '0.00')))
        prop_in = get_user_proposed_inflow(line)
        if prop_in is not None:
            inflow_proposed += money(prop_in)
        elif line.approved_inflow_amount is not None:
            inflow_proposed += money(line.approved_inflow_amount)
        if line.approved_inflow_amount is not None:
            inflow_approved += money(line.approved_inflow_amount)

    outflow_proposed = agg['user_proposed'] or ZERO
    outflow_actual = agg['prev_actual'] or ZERO
    outflow_budget = agg['prev_budget'] or ZERO
    outflow_suggested = agg['system_suggested'] or ZERO

    return {
        'previous_budget_total': outflow_budget,
        'previous_actual_total': outflow_actual,
        'routine_total': agg['routine'] or ZERO,
        'continuing_total': agg['continuing'] or ZERO,
        'management_continuing_total': management_continuing,
        'management_additional_total': management_additional,
        'management_other_total': management_other,
        'additional_total': agg['addl'] or ZERO,
        'one_time_total': agg['onetime'] or ZERO,
        'known_changes_total': agg['known_changes'] or ZERO,
        'personnel_effect_total': agg['personnel'] or ZERO,
        'system_suggested_total': outflow_suggested,
        'user_proposed_total': outflow_proposed,
        'approved_total': agg['approved'] or ZERO,
        'diff_from_prev_actual': outflow_proposed - outflow_actual,
        'diff_from_prev_budget': outflow_proposed - outflow_budget,
        # Inflows:
        'inflow_previous_budget_total': inflow_prev_budget,
        'inflow_previous_actual_total': inflow_prev_actual,
        'inflow_system_suggested_total': inflow_suggested,
        'inflow_user_proposed_total': inflow_proposed,
        'inflow_approved_total': inflow_approved,
        'inflow_diff_from_prev_actual': inflow_proposed - inflow_prev_actual,
        'inflow_diff_from_prev_budget': inflow_proposed - inflow_prev_budget,
        # Net balance:
        'net_proposed_balance': inflow_proposed - outflow_proposed,
        'net_actual_balance': inflow_prev_actual - outflow_actual,
        'net_budget_balance': inflow_prev_budget - outflow_budget,
        'net_suggested_balance': inflow_suggested - outflow_suggested,
        'line_count': lines.count(),
    }