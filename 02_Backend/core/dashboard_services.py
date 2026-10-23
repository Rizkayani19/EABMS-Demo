from datetime import date
from decimal import Decimal
from core.services import (
    get_opening_balance, get_total_actual_inflows, get_total_actual_outflows,
    get_total_pass_through, get_total_net_outflows,
    get_balance_available, get_total_approved_budget, get_total_approved_inflow_budget,
    get_budget_consumed, get_inflow_budget_consumed, get_balance_of_budget,
    get_inflow_budget_balance, get_net_budget_balance, get_budget_utilisation,
    get_inflow_budget_utilisation, get_reimbursement_summary,
    get_pass_through_inflows,
)
from reports.services import (
    build_monthly_trend, build_budget_utilisation,
    build_routine_vs_addl, build_pass_through_summary,
    build_pending_reimbursements,
)


def get_dashboard_data(account, fy):
    filters = {'account': account, 'financial_year': fy}

    ob = get_opening_balance(account, fy)
    inflows = get_total_actual_inflows(account, fy)
    pt_inflows = get_pass_through_inflows(account, fy)
    normal_inflows = inflows - pt_inflows
    outflows = get_total_actual_outflows(account, fy)
    pass_through_total = get_total_pass_through(account, fy)
    net_outflows = outflows - pass_through_total
    bal_avail = get_balance_available(account, fy)

    approved_outflow_budget = get_total_approved_budget(account, fy)
    approved_inflow_budget = get_total_approved_inflow_budget(account, fy)
    is_future_budget_active = False
    active_future_budget = None

    if approved_outflow_budget == Decimal('0.00') and approved_inflow_budget == Decimal('0.00'):
        from core.models import FutureBudget
        fb = FutureBudget.objects.filter(account=account, target_fy=fy).exclude(status=FutureBudget.Status.CLOSED).order_by('-created_at').first()
        if fb:
            is_future_budget_active = True
            active_future_budget = fb
            from core.future_budget_services import get_future_budget_summary
            from core.future_budget_inflow_proposal import get_user_proposed_inflow
            fb_summary = get_future_budget_summary(fb)
            prop_out = fb_summary.get('user_proposed_total')
            if prop_out is None or prop_out == Decimal('0.00'):
                prop_out = fb_summary.get('system_suggested_total') or Decimal('0.00')
            approved_outflow_budget = prop_out

            prop_in = Decimal('0.00')
            for l in fb.lines.all():
                val = get_user_proposed_inflow(l)
                if val is not None:
                    prop_in += val
                elif l.approved_inflow_amount is not None:
                    prop_in += l.approved_inflow_amount
            approved_inflow_budget = prop_in

    approved_net_budget = approved_inflow_budget - approved_outflow_budget
    outflow_consumed = get_budget_consumed(account, fy)
    inflow_consumed = get_inflow_budget_consumed(account, fy)
    outflow_budget_balance = approved_outflow_budget - outflow_consumed
    inflow_budget_balance = approved_inflow_budget - inflow_consumed
    net_budget_balance = approved_net_budget - (inflow_consumed - outflow_consumed)
    outflow_budget_utilisation = (outflow_consumed / approved_outflow_budget * Decimal('100')) if approved_outflow_budget > 0 else None
    inflow_budget_utilisation = (inflow_consumed / approved_inflow_budget * Decimal('100')) if approved_inflow_budget > 0 else None

    today = date.today()
    if today < fy.start_date or today > fy.end_date:
        today = fy.end_date

    this_month_start = today.replace(day=1)
    import calendar
    last_day = calendar.monthrange(today.year, today.month)[1]
    this_month_end = today.replace(day=last_day)

    this_month_inflows = get_total_actual_inflows(account, fy, this_month_start, this_month_end) or Decimal('0.00')
    this_month_outflows = get_total_actual_outflows(account, fy, this_month_start, this_month_end) or Decimal('0.00')

    monthly_trend = build_monthly_trend(filters)
    routine_addl = build_routine_vs_addl(filters)
    routine_outflows = sum(item.get('routine', Decimal('0.00')) if 'routine' in item else (item.get('amount', Decimal('0.00')) if 'Routine' in item.get('nature', '') else Decimal('0.00')) for item in routine_addl)
    addl_outflows = sum(item.get('addl', Decimal('0.00')) if 'addl' in item else (item.get('amount', Decimal('0.00')) if ('Addl' in item.get('nature', '') or 'Additional' in item.get('nature', '')) else Decimal('0.00')) for item in routine_addl)

    pt_summary = build_pass_through_summary(filters)
    pt_outflows = pt_summary[0]['pass_through_outflows'] if pt_summary else Decimal('0.00')

    from core.models import Transaction
    pt_count = Transaction.objects.filter(account=account, financial_year=fy, pass_through=True, status='ACTIVE').count()

    pending_reimbursements = build_pending_reimbursements(filters)
    pending_reimb_total = sum(item['pending'] for item in pending_reimbursements)
    pending_reimb_count = len(pending_reimbursements)

    budget_util_list = build_budget_utilisation(filters)
    top_budget_heads = sorted(budget_util_list, key=lambda x: x['budget_consumed'], reverse=True)[:5]

    alerts = []
    if bal_avail < 0:
        alerts.append({'type': 'ALERT', 'message': f'Negative balance available: Rs {bal_avail:,.2f}'})
    if approved_outflow_budget > 0 and outflow_consumed > approved_outflow_budget:
        alerts.append({'type': 'ALERT', 'message': 'Total expenditure has exceeded the approved outflow budget.'})
    elif outflow_budget_utilisation is not None and outflow_budget_utilisation > 80:
        alerts.append({'type': 'WARNING', 'message': f'Outflow budget utilisation is high ({outflow_budget_utilisation:.1f}%).'})
    if approved_inflow_budget > 0 and inflow_consumed > approved_inflow_budget:
        alerts.append({'type': 'ALERT', 'message': 'Actual inflows have exceeded the approved inflow budget.'})
    elif inflow_budget_utilisation is not None and inflow_budget_utilisation > 80:
        alerts.append({'type': 'WARNING', 'message': f'Inflow budget utilisation is high ({inflow_budget_utilisation:.1f}%).'})

    for item in budget_util_list:
        if item['budget_consumed'] > item['approved_budget'] and item['approved_budget'] > 0:
            alerts.append({'type': 'WARNING', 'message': f"Account Head '{item['account_head']}' is over budget."})

    if pending_reimb_count > 0:
        alerts.append({'type': 'WARNING', 'message': f'There are {pending_reimb_count} pending reimbursements totaling Rs {pending_reimb_total:,.2f}.'})

    from reports.services import build_continuing_reqs
    cont_reqs = build_continuing_reqs(filters)
    cont_outflows = sum(item.get('amount', Decimal('0.00')) for item in cont_reqs)
    new_outflows = sum(item.get('amount', Decimal('0.00')) for item in routine_addl if 'New' in item.get('nature', ''))

    return {
        'opening_balance': ob,
        'total_inflows': inflows,
        'normal_inflows': normal_inflows,
        'pt_inflows': pt_inflows,
        'total_outflows': outflows,
        'pass_through_total': pass_through_total,
        'net_outflows': net_outflows,
        'balance_available': bal_avail,
        'approved_budget': approved_outflow_budget,
        'approved_outflow_budget': approved_outflow_budget,
        'approved_inflow_budget': approved_inflow_budget,
        'approved_net_budget': approved_net_budget,
        'budget_consumed': outflow_consumed,
        'inflow_budget_consumed': inflow_consumed,
        'balance_of_budget': outflow_budget_balance,
        'inflow_budget_balance': inflow_budget_balance,
        'net_budget_balance': net_budget_balance,
        'budget_utilisation': outflow_budget_utilisation,
        'inflow_budget_utilisation': inflow_budget_utilisation,
        'this_month_inflows': this_month_inflows,
        'this_month_outflows': this_month_outflows,
        'since_start_inflows': inflows,
        'since_start_outflows': outflows,
        'fy_inflows': inflows,
        'fy_outflows': outflows,
        'monthly_trend': monthly_trend,
        'routine_outflows': routine_outflows,
        'addl_outflows': addl_outflows,
        'cont_outflows': cont_outflows,
        'new_outflows': new_outflows,
        'pt_count': pt_count,
        'pt_outflows': pt_outflows,
        'pending_reimb_count': pending_reimb_count,
        'pending_reimb_total': pending_reimb_total,
        'reimbursement_summary': get_reimbursement_summary(account, fy) or {'expected': Decimal('0.00'), 'received': Decimal('0.00'), 'pending': Decimal('0.00')},
        'top_budget_heads': top_budget_heads,
        'alerts': alerts,
        'is_future_budget_active': is_future_budget_active,
        'active_future_budget': active_future_budget,
    }
