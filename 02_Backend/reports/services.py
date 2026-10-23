from decimal import Decimal
from django.db.models import Sum, F, Q
from core.models import Transaction, Budget, BudgetLine, Reimbursement, Account, FinancialYear, MajorHead, SubHead, AccountHead
from core.services import (
    get_total_actual_inflows, get_total_actual_outflows,
    get_opening_balance, get_balance_available,
    get_total_approved_budget, get_budget_consumed, get_balance_of_budget,
    get_budget_utilisation, get_pass_through_outflows, get_pass_through_inflows,
    get_reimbursement_summary
)
from .registry import registry, ReportDefinition


def apply_filters(qs, filters):
    if filters.get('account'):
        if hasattr(qs.model, 'account'): qs = qs.filter(account=filters['account'])
        elif hasattr(qs.model, 'budget'): qs = qs.filter(budget__account=filters['account'])
        elif hasattr(qs.model, 'original_outflow'): qs = qs.filter(original_outflow__account=filters['account'])
    if filters.get('financial_year'):
        if hasattr(qs.model, 'financial_year'): qs = qs.filter(financial_year=filters['financial_year'])
        elif hasattr(qs.model, 'budget'): qs = qs.filter(budget__financial_year=filters['financial_year'])
        elif hasattr(qs.model, 'original_outflow'): qs = qs.filter(original_outflow__financial_year=filters['financial_year'])
    if filters.get('start_date') and hasattr(qs.model, 'transaction_date'): qs = qs.filter(transaction_date__gte=filters['start_date'])
    if filters.get('end_date') and hasattr(qs.model, 'transaction_date'): qs = qs.filter(transaction_date__lte=filters['end_date'])
    if filters.get('major_head'): qs = qs.filter(major_head=filters['major_head'])
    if filters.get('sub_head'): qs = qs.filter(sub_head=filters['sub_head'])
    if filters.get('account_head'): qs = qs.filter(account_head=filters['account_head'])
    if filters.get('unit'): qs = qs.filter(unit=filters['unit'])
    if filters.get('unit_ids') and hasattr(qs.model, 'unit'): qs = qs.filter(unit_id__in=filters['unit_ids'])
    if filters.get('internal_section_ids') and qs.model is Transaction: qs = qs.filter(transaction_sections__id__in=filters['internal_section_ids']).distinct()
    if filters.get('direction'): qs = qs.filter(direction=filters['direction'])
    if filters.get('outflow_nature'): qs = qs.filter(outflow_nature=filters['outflow_nature'])
    if filters.get('pass_through') is not None: qs = qs.filter(pass_through=filters['pass_through'])
    if filters.get('status'): qs = qs.filter(status=filters['status'])
    return qs


def build_account_summary(filters):
    acc, fy = filters.get('account'), filters.get('financial_year')
    if not acc or not fy: return []
    start_date, end_date = filters.get('start_date'), filters.get('end_date')
    if start_date or end_date:
        from core.services import get_period_summary, get_pass_through_inflows, get_pass_through_outflows
        period_data = get_period_summary(acc, fy, start_date or fy.start_date, end_date)
        ob = period_data['period_opening_balance']
        inflows = period_data['period_inflows']
        outflows = period_data['period_outflows']
        bal = period_data['period_closing_balance']
        pt_in = get_pass_through_inflows(acc, fy, start_date or fy.start_date, end_date)
        pt_out = get_pass_through_outflows(acc, fy, start_date or fy.start_date, end_date)
    else:
        from core.services import get_pass_through_inflows, get_pass_through_outflows
        ob = get_opening_balance(acc, fy)
        inflows = get_total_actual_inflows(acc, fy)
        outflows = get_total_actual_outflows(acc, fy)
        bal = get_balance_available(acc, fy)
        pt_in = get_pass_through_inflows(acc, fy)
        pt_out = get_pass_through_outflows(acc, fy)
    op_in = max(Decimal('0.00'), inflows - pt_in)
    op_out = max(Decimal('0.00'), outflows - pt_out)
    appr, cons = get_total_approved_budget(acc, fy), get_budget_consumed(acc, fy)
    return [{
        'account': acc.name,
        'opening_balance': ob,
        'operational_inflows': op_in,
        'pass_through_inflows': pt_in,
        'total_inflows': inflows,
        'operational_outflows': op_out,
        'pass_through_outflows': pt_out,
        'total_outflows': outflows,
        'balance_available': bal,
        'approved_budget': appr,
        'budget_consumed': cons,
        'balance_of_budget': get_balance_of_budget(acc, fy),
        'budget_utilisation': get_budget_utilisation(acc, fy)
    }]


def _base_grouped_outflows(filters, group_by_fields, annotate_fields):
    return apply_filters(Transaction.objects.filter(status='ACTIVE', direction='OUTFLOW'), filters).values(*group_by_fields).annotate(**annotate_fields).order_by(*group_by_fields)


def _base_grouped_inflows(filters, group_by_fields, annotate_fields):
    return apply_filters(Transaction.objects.filter(status='ACTIVE', direction='INFLOW'), filters).values(*group_by_fields).annotate(**annotate_fields).order_by(*group_by_fields)


def _get_fy_months(filters):
    fy = filters.get('financial_year')
    months = []
    if fy and fy.start_date and fy.end_date:
        import datetime
        start_d = datetime.date.fromisoformat(str(fy.start_date)) if isinstance(fy.start_date, str) else fy.start_date
        end_d = datetime.date.fromisoformat(str(fy.end_date)) if isinstance(fy.end_date, str) else fy.end_date
        curr_y, curr_m = start_d.year, start_d.month
        end_y, end_m = end_d.year, end_d.month
        while (curr_y < end_y) or (curr_y == end_y and curr_m <= end_m):
            months.append(f"{curr_y:04d}-{curr_m:02d}")
            if curr_m == 12:
                curr_y += 1
                curr_m = 1
            else:
                curr_m += 1
    return months


def build_monthly_inflows(filters):
    qs = apply_filters(Transaction.objects.filter(status='ACTIVE', direction='INFLOW'), filters)
    data = {m: {'month': m, 'operational_inflows': Decimal('0.00'), 'pass_through': Decimal('0.00'), 'amount': Decimal('0.00')} for m in _get_fy_months(filters)}
    for tx in qs:
        m = tx.transaction_date.strftime('%Y-%m')
        row = data.setdefault(m, {'month': m, 'operational_inflows': Decimal('0.00'), 'pass_through': Decimal('0.00'), 'amount': Decimal('0.00')})
        if tx.pass_through:
            row['pass_through'] += tx.amount
        else:
            row['operational_inflows'] += tx.amount
        row['amount'] += tx.amount
    return sorted(data.values(), key=lambda x: x['month'])


def build_monthly_outflows(filters):
    qs = apply_filters(Transaction.objects.filter(status='ACTIVE', direction='OUTFLOW'), filters)
    data = {m: {'month': m, 'operational_outflows': Decimal('0.00'), 'pass_through': Decimal('0.00'), 'amount': Decimal('0.00')} for m in _get_fy_months(filters)}
    for tx in qs:
        m = tx.transaction_date.strftime('%Y-%m')
        row = data.setdefault(m, {'month': m, 'operational_outflows': Decimal('0.00'), 'pass_through': Decimal('0.00'), 'amount': Decimal('0.00')})
        if tx.pass_through:
            row['pass_through'] += tx.amount
        else:
            row['operational_outflows'] += tx.amount
        row['amount'] += tx.amount
    return sorted(data.values(), key=lambda x: x['month'])


def build_reimbursements(filters):
    acc, fy = filters.get('account'), filters.get('financial_year')
    if not acc or not fy: return []
    from .models import Reimbursement
    qs = Reimbursement.objects.filter(
        original_outflow__account=acc,
        original_outflow__financial_year=fy,
        original_outflow__pass_through=False,
    )
    from django.db.models import Sum
    vals = qs.aggregate(expected=Sum('expected_amount'), received=Sum('received_amount'))
    expected = (vals['expected'] or Decimal('0.00'))
    received = (vals['received'] or Decimal('0.00'))
    return [{'account': acc.name, 'expected': expected, 'received': received, 'pending': expected - received}]


def build_pending_reimbursements(filters):
    qs = apply_filters(Reimbursement.objects.filter(status__in=['EXPECTED', 'PARTIALLY_RECEIVED']), filters); res = []
    for r in qs:
        res.append({'reference': r.reference, 'outflow_tx': r.original_outflow.transaction_number if r.original_outflow else '', 'expected': r.expected_amount, 'received': r.received_amount, 'pending': r.expected_amount-r.received_amount})
    return res


def build_budget_vs_actual(filters):
    acc, fy = filters.get('account'), filters.get('financial_year')
    if not acc or not fy: return []
    bl_qs = apply_filters(BudgetLine.objects.filter(budget__account=acc, budget__financial_year=fy, budget__status='APPROVED'), filters); data = {}
    for bl in bl_qs:
        key = bl.account_head_id
        data.setdefault(key, {'account_head': bl.account_head.name if bl.account_head else 'Other', 'approved_budget': Decimal('0.00'), 'budget_consumed': Decimal('0.00')})
        data[key]['approved_budget'] += bl.amount
    for tx in apply_filters(Transaction.objects.filter(account=acc, financial_year=fy, direction='OUTFLOW', status='ACTIVE', pass_through=False), filters):
        key = tx.account_head_id
        data.setdefault(key, {'account_head': tx.account_head.name if tx.account_head else 'Other', 'approved_budget': Decimal('0.00'), 'budget_consumed': Decimal('0.00')})
        data[key]['budget_consumed'] += tx.amount
    for row in data.values():
        row['balance_of_budget'] = row['approved_budget'] - row['budget_consumed']
        row['utilisation_pct'] = (row['budget_consumed'] / row['approved_budget'] * 100) if row['approved_budget'] else None
    return sorted(data.values(), key=lambda x: x['account_head'])


def build_routine_vs_addl(filters):
    qs=apply_filters(Transaction.objects.filter(status='ACTIVE',direction='OUTFLOW'),filters); months=sorted({tx.transaction_date.strftime('%Y-%m') for tx in qs if tx.transaction_date}); data={m:{'month':m,'routine':Decimal('0.00'),'addl':Decimal('0.00'),'pass_through':Decimal('0.00'),'total':Decimal('0.00')} for m in months}
    for tx in qs:
        m=tx.transaction_date.strftime('%Y-%m'); row=data.setdefault(m,{'month':m,'routine':Decimal('0.00'),'addl':Decimal('0.00'),'pass_through':Decimal('0.00'),'total':Decimal('0.00')}); nat=(tx.outflow_nature.name if tx.outflow_nature else '').lower()
        if tx.pass_through or 'pass' in nat: row['pass_through'] += tx.amount
        elif 'add' in nat: row['addl'] += tx.amount
        else: row['routine'] += tx.amount
        row['total'] += tx.amount
    return [data[m] for m in sorted(data)]


def build_account_head_summary(filters):
    qs=apply_filters(Transaction.objects.filter(status='ACTIVE',direction='OUTFLOW',pass_through=False),filters); data={}
    for tx in qs:
        ah=tx.account_head.name if tx.account_head else 'None'; data.setdefault(ah,{'account_head':ah,'amount':Decimal('0.00')})['amount'] += tx.amount
    return sorted(data.values(),key=lambda x:x['account_head'])


def build_sub_head_summary(filters):
    qs=apply_filters(Transaction.objects.filter(status='ACTIVE',direction='OUTFLOW',pass_through=False),filters); data={}
    for tx in qs:
        sh=tx.sub_head.name if tx.sub_head else 'None'; data.setdefault(sh,{'sub_head':sh,'amount':Decimal('0.00')})['amount'] += tx.amount
    return sorted(data.values(),key=lambda x:x['sub_head'])


def build_major_head_summary(filters):
    acc = filters.get('account')
    from core.models import MajorHead
    data = {}
    if acc:
        for mh in MajorHead.objects.filter(account=acc).order_by('name'):
            data[mh.name] = {
                'major_head': mh.name,
                'operational_outflows': Decimal('0.00'),
                'pass_through': Decimal('0.00'),
                'amount': Decimal('0.00'),
            }
    qs = apply_filters(Transaction.objects.filter(status='ACTIVE', direction='OUTFLOW'), filters)
    for tx in qs:
        mh_name = tx.major_head.name if tx.major_head else 'None'
        row = data.setdefault(mh_name, {
            'major_head': mh_name,
            'operational_outflows': Decimal('0.00'),
            'pass_through': Decimal('0.00'),
            'amount': Decimal('0.00'),
        })
        if tx.pass_through:
            row['pass_through'] += tx.amount
        else:
            row['operational_outflows'] += tx.amount
        row['amount'] += tx.amount
    return sorted(data.values(), key=lambda x: x['major_head'])


def build_monthly_trend(filters):
    data = {
        m: {
            'month': m,
            'operational_inflows': Decimal('0.00'),
            'pass_through_inflows': Decimal('0.00'),
            'inflows': Decimal('0.00'),
            'operational_outflows': Decimal('0.00'),
            'pass_through': Decimal('0.00'),
            'outflows': Decimal('0.00'),
        }
        for m in _get_fy_months(filters)
    }
    for tx in apply_filters(Transaction.objects.filter(status='ACTIVE', direction='INFLOW'), filters):
        m = tx.transaction_date.strftime('%Y-%m')
        row = data.setdefault(m, {
            'month': m,
            'operational_inflows': Decimal('0.00'),
            'pass_through_inflows': Decimal('0.00'),
            'inflows': Decimal('0.00'),
            'operational_outflows': Decimal('0.00'),
            'pass_through': Decimal('0.00'),
            'outflows': Decimal('0.00'),
        })
        if tx.pass_through:
            row['pass_through_inflows'] += tx.amount
        else:
            row['operational_inflows'] += tx.amount
        row['inflows'] += tx.amount
    for tx in apply_filters(Transaction.objects.filter(status='ACTIVE', direction='OUTFLOW'), filters):
        m = tx.transaction_date.strftime('%Y-%m')
        row = data.setdefault(m, {
            'month': m,
            'operational_inflows': Decimal('0.00'),
            'pass_through_inflows': Decimal('0.00'),
            'inflows': Decimal('0.00'),
            'operational_outflows': Decimal('0.00'),
            'pass_through': Decimal('0.00'),
            'outflows': Decimal('0.00'),
        })
        if tx.pass_through:
            row['pass_through'] += tx.amount
        else:
            row['operational_outflows'] += tx.amount
        row['outflows'] += tx.amount
    return [{**data[m], 'balance_movement': data[m]['inflows'] - data[m]['outflows']} for m in sorted(data)]


def build_fy_summary(filters): return build_account_summary(filters)

def build_continuing_reqs(filters):
    qs=apply_filters(Transaction.objects.filter(status='ACTIVE',direction='OUTFLOW',outflow_nature__name__icontains='Continuing'),filters); data={}
    for tx in qs:
        sh=tx.sub_head.name if tx.sub_head else 'None'; data.setdefault(sh,{'sub_head':sh,'amount':Decimal('0.00')})['amount'] += tx.amount
    return list(data.values())


def build_addl_expenditure(filters):
    qs=apply_filters(Transaction.objects.filter(status='ACTIVE',direction='OUTFLOW').filter(Q(outflow_nature__name__icontains='Additional')|Q(outflow_nature__name__icontains='Addl')),filters); data={}
    for tx in qs:
        sh=tx.sub_head.name if tx.sub_head else 'None'; data.setdefault(sh,{'sub_head':sh,'amount':Decimal('0.00')})['amount'] += tx.amount
    return list(data.values())


def build_pass_through_summary(filters):
    acc, fy = filters.get('account'), filters.get('financial_year')
    if not acc or not fy: return []
    start, end = filters.get('start_date'), filters.get('end_date')
    total_in=get_total_actual_inflows(acc,fy,start,end); total_out=get_total_actual_outflows(acc,fy,start,end)
    pt_in=get_pass_through_inflows(acc,fy,start,end); pt_out=get_pass_through_outflows(acc,fy,start,end)
    return [{'total_inflows':total_in,'pass_through_inflows':pt_in,'other_inflows':total_in-pt_in,'total_outflows':total_out,'pass_through_outflows':pt_out,'other_outflows':total_out-pt_out}]


def build_budget_utilisation(filters):
    acc, fy = filters.get('account'), filters.get('financial_year')
    if not acc or not fy: return []
    bl_qs = apply_filters(BudgetLine.objects.filter(budget__account=acc, budget__financial_year=fy, budget__status='APPROVED'), filters)
    
    first_b = Budget.objects.filter(account=acc, financial_year=fy, status='APPROVED').first()
    is_sf_basis = (
        (first_b and first_b.budget_allocation_basis == 'SUB_FUND')
        or bl_qs.filter(account_head__isnull=True, major_head__isnull=False).exists()
        or (getattr(acc, 'budget_allocation_basis', None) == 'SUB_FUND' and not bl_qs.filter(account_head__isnull=False).exists())
    )

    data = {}
    if is_sf_basis:
        for bl in bl_qs:
            sf_name = bl.major_head.name if bl.major_head else (bl.account_head.name if bl.account_head else 'Other')
            row = data.setdefault(sf_name, {'account_head': sf_name, 'sub_fund': sf_name, 'approved_budget': Decimal('0.00'), 'budget_consumed': Decimal('0.00')})
            row['approved_budget'] += bl.amount
        tx_qs = apply_filters(Transaction.objects.filter(account=acc, financial_year=fy, direction='OUTFLOW', status='ACTIVE', pass_through=False), filters)
        for tx in tx_qs:
            sf_name = tx.major_head.name if tx.major_head else (tx.account_head.major_head.name if tx.account_head and tx.account_head.major_head else 'Other')
            row = data.setdefault(sf_name, {'account_head': sf_name, 'sub_fund': sf_name, 'approved_budget': Decimal('0.00'), 'budget_consumed': Decimal('0.00')})
            row['budget_consumed'] += tx.amount
    else:
        for bl in bl_qs:
            ah_name = bl.account_head.name if bl.account_head else 'Other'
            row = data.setdefault(ah_name, {'account_head': ah_name, 'approved_budget': Decimal('0.00'), 'budget_consumed': Decimal('0.00')})
            row['approved_budget'] += bl.amount
        tx_qs = apply_filters(Transaction.objects.filter(account=acc, financial_year=fy, direction='OUTFLOW', status='ACTIVE', pass_through=False), filters)
        for tx in tx_qs:
            ah_name = tx.account_head.name if tx.account_head else 'Other'
            row = data.setdefault(ah_name, {'account_head': ah_name, 'approved_budget': Decimal('0.00'), 'budget_consumed': Decimal('0.00')})
            row['budget_consumed'] += tx.amount

    rows = []
    for head_name, row in sorted(data.items()):
        row['balance_of_budget'] = row['approved_budget'] - row['budget_consumed']
        row['utilisation_pct'] = (row['budget_consumed'] / row['approved_budget'] * 100) if row['approved_budget'] else None
        rows.append(row)
    return rows


def build_yoy_comparative(filters):
    """
    Year-on-Year (YoY) Comparative Report:
    Compares Prior Financial Year Actual vs Current Financial Year Approved Budget & Actual Consumed,
    aggregated cleanly by Account Head (Sub Heads removed per operational guidelines).
    """
    acc = filters.get('account')
    curr_fy = filters.get('financial_year')
    selected_fys = filters.get('selected_fys', [])
    if not acc or not curr_fy:
        return []

    prior_fy = None
    if len(selected_fys) >= 2:
        # If user explicitly selected multiple FYs, compare first two in order
        if selected_fys[0].pk == curr_fy.pk:
            prior_fy = selected_fys[1]
        else:
            prior_fy = selected_fys[0]
    else:
        # Determine chronologically previous FY
        all_fys = list(FinancialYear.objects.all().order_by('start_date'))
        curr_idx = next((i for i, f in enumerate(all_fys) if f.pk == curr_fy.pk), -1)
        if curr_idx > 0:
            prior_fy = all_fys[curr_idx - 1]
        elif len(all_fys) >= 2:
            prior_fy = all_fys[0] if all_fys[0].pk != curr_fy.pk else all_fys[1]

    # Current Year Budget (aggregated at Account Head level)
    curr_bl_qs = apply_filters(
        BudgetLine.objects.filter(budget__account=acc, budget__financial_year=curr_fy, budget__status='APPROVED'),
        filters
    )
    data = {}
    for bl in curr_bl_qs:
        key = bl.account_head_id
        data.setdefault(key, {
            'account_head': bl.account_head.name if bl.account_head else '—',
            'prior_actual': Decimal('0.00'),
            'curr_budget': Decimal('0.00'),
            'curr_actual': Decimal('0.00'),
        })
        data[key]['curr_budget'] += bl.amount

    # Current Year Outflows (excl pass-through for true operational expenditure)
    curr_tx_qs = apply_filters(
        Transaction.objects.filter(
            account=acc, financial_year=curr_fy, direction='OUTFLOW',
            status='ACTIVE', pass_through=False
        ),
        filters
    )
    for tx in curr_tx_qs:
        key = tx.account_head_id
        data.setdefault(key, {
            'account_head': tx.account_head.name if tx.account_head else '—',
            'prior_actual': Decimal('0.00'),
            'curr_budget': Decimal('0.00'),
            'curr_actual': Decimal('0.00'),
        })
        data[key]['curr_actual'] += tx.amount

    # Prior Year Outflows (excl pass-through)
    if prior_fy:
        prior_filters = {**filters, 'financial_year': prior_fy}
        prior_tx_qs = apply_filters(
            Transaction.objects.filter(
                account=acc, financial_year=prior_fy, direction='OUTFLOW',
                status='ACTIVE', pass_through=False
            ),
            prior_filters
        )
        for tx in prior_tx_qs:
            key = tx.account_head_id
            data.setdefault(key, {
                'account_head': tx.account_head.name if tx.account_head else '—',
                'prior_actual': Decimal('0.00'),
                'curr_budget': Decimal('0.00'),
                'curr_actual': Decimal('0.00'),
            })
            data[key]['prior_actual'] += tx.amount

    # Compute variance, util % and YoY growth %
    for row in data.values():
        c_bud = row['curr_budget']
        c_act = row['curr_actual']
        p_act = row['prior_actual']
        row['budget_balance'] = c_bud - c_act
        row['curr_util_pct'] = (c_act / c_bud * 100) if c_bud else None
        yoy_diff = c_act - p_act
        row['yoy_variance'] = yoy_diff
        row['yoy_growth_pct'] = (yoy_diff / p_act * 100) if p_act else None

    return sorted(data.values(), key=lambda x: x['account_head'])


def build_consolidated(filters):
    fy=filters.get('financial_year')
    if not fy: return []
    return [{'account':acc.name,'approved_budget':get_total_approved_budget(acc,fy),'inflows':get_total_actual_inflows(acc,fy),'outflows':get_total_actual_outflows(acc,fy),'balance_available':get_balance_available(acc,fy)} for acc in Account.objects.filter(is_active=True)]

registry.register(ReportDefinition(slug='account-summary',title='Acct Summary',description='Provides an executive overview of fund balances, comparing opening balance, operational & pass-through inflows, actual expenditures, and remaining cash position against the approved budget.',builder_func=build_account_summary,columns=[{'key':'account','label':'Acct'},{'key':'opening_balance','label':'Opening Balance'},{'key':'operational_inflows','label':'Operational Inflows'},{'key':'pass_through_inflows','label':'PT Inflows'},{'key':'total_inflows','label':'Total Inflows'},{'key':'operational_outflows','label':'Operational Outflows'},{'key':'pass_through_outflows','label':'PT Outflows'},{'key':'total_outflows','label':'Total Outflows'},{'key':'balance_available','label':'Balance Available'},{'key':'approved_budget','label':'Approved Budget'},{'key':'budget_consumed','label':'Budget Consumed'},{'key':'balance_of_budget','label':'Balance of Budget'},{'key':'budget_utilisation','label':'Utilisation %'}],supported_filters=['account','financial_year','start_date','end_date'],totals=['operational_inflows','pass_through_inflows','total_inflows','operational_outflows','pass_through_outflows','total_outflows'],display_in_millions=True))
registry.register(ReportDefinition(slug='monthly-inflows',title='Monthly Inflows',description='Tracks month-by-month inflow receipts across the Fin Yr, detailing operational receipts, internal pass-through transfers, and total gross inflows.',builder_func=build_monthly_inflows,columns=[{'key':'month','label':'Month'},{'key':'operational_inflows','label':'Operational Inflows (Excl. Pass-Through)'},{'key':'pass_through','label':'Pass-Through Inflows (Internal)'},{'key':'amount','label':'Total Inflows (Gross)'}],supported_filters=['account','financial_year','start_date','end_date'],totals=['operational_inflows','pass_through','amount'],display_in_millions=True))
registry.register(ReportDefinition(slug='monthly-outflows',title='Monthly Outflows',description='Breaks down monthly expenditure trends, detailing operational expenditures, internal pass-through transfers, and total gross outflows across the Fin Yr.',builder_func=build_monthly_outflows,columns=[{'key':'month','label':'Month'},{'key':'operational_outflows','label':'Operational Outflows (Excl. Pass-Through)'},{'key':'pass_through','label':'Pass-Through Transfers (Internal)'},{'key':'amount','label':'Total Outflows (Gross)'}],supported_filters=['account','financial_year','start_date','end_date','major_head','sub_head','account_head'],totals=['operational_outflows','pass_through','amount'],display_in_millions=True))
registry.register(ReportDefinition(slug='reimbursements',title='Reimbursements Summary',description='Monitors claims and recoupments submitted to external departments, detailing expected amounts, funds received, and pending balances.',builder_func=build_reimbursements,columns=[{'key':'account','label':'Acct'},{'key':'expected','label':'Expected'},{'key':'received','label':'Received'},{'key':'pending','label':'Pending'}],supported_filters=['account','financial_year'],totals=['expected','received','pending'],display_in_millions=True))
registry.register(ReportDefinition(slug='budget-vs-actual',title='Budget vs Actual',description='Compares allocated budget allocations against actual expenditures by Acct Head to highlight surplus or deficit.',builder_func=build_budget_vs_actual,columns=[{'key':'account_head','label':'Acct Head'},{'key':'approved_budget','label':'Approved'},{'key':'budget_consumed','label':'Consumed'},{'key':'balance_of_budget','label':'Balance'},{'key':'utilisation_pct','label':'Utilisation %'}],supported_filters=['account','financial_year','major_head','account_head'],totals=['approved_budget','budget_consumed','balance_of_budget'],display_in_millions=True))
registry.register(ReportDefinition(slug='routine-vs-addl',title='Routine vs Addl Outflows',description='Analyzes monthly outflows divided into Routine operational expenditures, Additional sanctioned requirements, and Pass-through internal Tfrs.',builder_func=build_routine_vs_addl,columns=[{'key':'month','label':'Month'},{'key':'routine','label':'Routine'},{'key':'addl','label':'Additional'},{'key':'pass_through','label':'Pass-through'},{'key':'total','label':'Total Outflows'}],supported_filters=['account','financial_year','start_date','end_date'],totals=['routine','addl','pass_through','total'],display_in_millions=True))
registry.register(ReportDefinition(slug='account-head-summary',title='Acct Head Summary',description='Presents cumulative expenditures aggregated by Acct Head (Tier 2) to evaluate budget consumption per operational head.',builder_func=build_account_head_summary,columns=[{'key':'account_head','label':'Acct Head'},{'key':'amount','label':'Amount'}],supported_filters=['account','financial_year','start_date','end_date'],totals=['amount'],display_in_millions=True))
registry.register(ReportDefinition(slug='sub-head-summary',title='Sub Head Summary',description='Provides detailed expenditures grouped by granular Sub Heads (Tier 3) within each parent Acct Head.',builder_func=build_sub_head_summary,columns=[{'key':'sub_head','label':'Sub Head'},{'key':'amount','label':'Amount'}],supported_filters=['account','financial_year','start_date','end_date','major_head'],totals=['amount'],display_in_millions=True))
registry.register(ReportDefinition(slug='major-head-summary',title='Sub Fund Summary',description='Aggregates expenditures by Sub Fund (Tier 1) across the organization to monitor strategic fund allocations.',builder_func=build_major_head_summary,columns=[{'key':'major_head','label':'Sub Fund'},{'key':'operational_outflows','label':'Operational Outflows (Excl. Pass-Through)'},{'key':'pass_through','label':'Pass-Through Transfers (Internal)'},{'key':'amount','label':'Total Outflows (Gross)'}],supported_filters=['account','financial_year','start_date','end_date'],totals=['operational_outflows','pass_through','amount'],display_in_millions=True))
registry.register(ReportDefinition(slug='monthly-trend',title='Monthly Trend',description='Summarizes monthly inflows and outflows, showing operational receipts, pass-through transfers, operational expenditure, and available balance across the financial year.',builder_func=build_monthly_trend,columns=[{'key':'month','label':'Month'},{'key':'operational_inflows','label':'Operational Inflows (Excl PT)'},{'key':'pass_through_inflows','label':'PT Inflows'},{'key':'inflows','label':'Total Inflows'},{'key':'operational_outflows','label':'Operational Outflows (Excl PT)'},{'key':'pass_through','label':'Pass-Through Tfrs'},{'key':'outflows','label':'Total Outflows'},{'key':'balance_movement','label':'Net Movement'}],supported_filters=['account','financial_year','start_date','end_date'],totals=['operational_inflows','pass_through_inflows','inflows','operational_outflows','pass_through','outflows','balance_movement'],display_in_millions=True))
registry.register(ReportDefinition(slug='fy-summary',title='Fin Yr Summary',description='Consolidates opening balance, operational & pass-through inflows, operational & pass-through outflows, and net closing available balance across the selected Fin Yr.',builder_func=build_fy_summary,columns=[{'key':'account','label':'Acct'},{'key':'opening_balance','label':'Opening'},{'key':'operational_inflows','label':'Operational Inflows (Excl PT)'},{'key':'pass_through_inflows','label':'PT Inflows'},{'key':'total_inflows','label':'Total Inflows'},{'key':'operational_outflows','label':'Operational Outflows (Excl PT)'},{'key':'pass_through_outflows','label':'PT Outflows'},{'key':'total_outflows','label':'Total Outflows'},{'key':'balance_available','label':'Balance'}],supported_filters=['account','financial_year'],totals=['operational_inflows','pass_through_inflows','total_inflows','operational_outflows','pass_through_outflows','total_outflows'],display_in_millions=True))
registry.register(ReportDefinition(slug='pass-through-summary',title='Pass-through Summary',description='Separates internal book Tfrs and pass-through Txns from actual operational revenues and true organizational expenditures.',builder_func=build_pass_through_summary,columns=[{'key':'total_inflows','label':'Total Inflows'},{'key':'pass_through_inflows','label':'Pass-through Inflows'},{'key':'other_inflows','label':'Other Inflows'},{'key':'total_outflows','label':'Total Outflows'},{'key':'pass_through_outflows','label':'Pass-through Outflows'},{'key':'other_outflows','label':'Other Outflows'}],supported_filters=['account','financial_year','start_date','end_date'],totals=[],display_in_millions=True))
registry.register(ReportDefinition(slug='budget-utilisation',title='Budget Utilisation',description='Details the utilization percentage of approved budget allocations by Account Head to flag over-consumed and under-utilized heads.',builder_func=build_budget_utilisation,columns=[{'key':'account_head','label':'Acct Head'},{'key':'approved_budget','label':'Approved Budget'},{'key':'budget_consumed','label':'Budget Consumed'},{'key':'balance_of_budget','label':'Balance of Budget'},{'key':'utilisation_pct','label':'Utilisation %'}],supported_filters=['account','financial_year','major_head','account_head','start_date','end_date'],totals=['approved_budget','budget_consumed','balance_of_budget'],display_in_millions=True))
registry.register(ReportDefinition(slug='yoy-comparative',title='YoY Comparative',description='Side-by-side comparative analysis of prior Fin Yr actual expenditure against current Fin Yr budget allocation and actual consumption, tracking year-on-year growth and operational variances by Account Head.',builder_func=build_yoy_comparative,columns=[{'key':'account_head','label':'Acct Head'},{'key':'prior_actual','label':'Prior Yr Actual'},{'key':'curr_budget','label':'Current Budget'},{'key':'curr_actual','label':'Current Consumed'},{'key':'budget_balance','label':'Budget Balance'},{'key':'curr_util_pct','label':'Current Util %'},{'key':'yoy_variance','label':'YoY Variance (+/-)'},{'key':'yoy_growth_pct','label':'YoY Growth %'}],supported_filters=['account','financial_year','major_head','account_head'],totals=['prior_actual','curr_budget','curr_actual','budget_balance'],display_in_millions=True))
def build_dynamic_transactions(filters):
    acc = filters.get('account')
    if not acc:
        return []

    qs = Transaction.objects.filter(account=acc, status=Transaction.Status.ACTIVE)

    fy = filters.get('financial_year')
    start_date = filters.get('start_date')
    end_date = filters.get('end_date')

    if start_date:
        qs = qs.filter(transaction_date__gte=start_date)
    if end_date:
        qs = qs.filter(transaction_date__lte=end_date)
    if not start_date and not end_date and fy:
        qs = qs.filter(financial_year=fy)

    direction = filters.get('direction')
    if direction in ('INFLOW', 'OUTFLOW'):
        qs = qs.filter(direction=direction)

    major_head = filters.get('major_head')
    if major_head:
        if isinstance(major_head, int) or (isinstance(major_head, str) and major_head.isdigit()):
            qs = qs.filter(major_head_id=int(major_head))
        elif hasattr(major_head, 'id'):
            qs = qs.filter(major_head=major_head)
        elif isinstance(major_head, str):
            qs = qs.filter(major_head__name__iexact=major_head)

    account_head = filters.get('account_head')
    if account_head:
        if isinstance(account_head, int) or (isinstance(account_head, str) and account_head.isdigit()):
            qs = qs.filter(account_head_id=int(account_head))
        elif hasattr(account_head, 'id'):
            qs = qs.filter(account_head=account_head)
        elif isinstance(account_head, str):
            qs = qs.filter(account_head__name__iexact=account_head)

    sub_head = filters.get('sub_head')
    if sub_head:
        if isinstance(sub_head, int) or (isinstance(sub_head, str) and sub_head.isdigit()):
            qs = qs.filter(sub_head_id=int(sub_head))
        elif hasattr(sub_head, 'id'):
            qs = qs.filter(sub_head=sub_head)
        elif isinstance(sub_head, str):
            qs = qs.filter(sub_head__name__iexact=sub_head)

    # Fund-specific filters
    unit = filters.get('unit')
    if unit:
        if isinstance(unit, int) or (isinstance(unit, str) and unit.isdigit()):
            qs = qs.filter(Q(unit_id=int(unit)) | Q(transaction_units__id=int(unit))).distinct()
        elif hasattr(unit, 'id'):
            qs = qs.filter(Q(unit=unit) | Q(transaction_units=unit)).distinct()

    internal_section = filters.get('internal_section')
    if internal_section:
        if isinstance(internal_section, int) or (isinstance(internal_section, str) and internal_section.isdigit()):
            qs = qs.filter(Q(internal_section_id=int(internal_section)) | Q(transaction_sections__id=int(internal_section))).distinct()
        elif hasattr(internal_section, 'id'):
            qs = qs.filter(Q(internal_section=internal_section) | Q(transaction_sections=internal_section)).distinct()

    cohort = filters.get('cohort')
    if cohort:
        if isinstance(cohort, int) or (isinstance(cohort, str) and cohort.isdigit()):
            qs = qs.filter(cohort_id=int(cohort))
        elif hasattr(cohort, 'id'):
            qs = qs.filter(cohort=cohort)

    package = filters.get('package')
    if package:
        if isinstance(package, int) or (isinstance(package, str) and package.isdigit()):
            qs = qs.filter(package_id=int(package))
        elif hasattr(package, 'id'):
            qs = qs.filter(package=package)

    tour_operator = filters.get('tour_operator')
    if tour_operator:
        if isinstance(tour_operator, int) or (isinstance(tour_operator, str) and tour_operator.isdigit()):
            qs = qs.filter(tour_operator_id=int(tour_operator))
        elif hasattr(tour_operator, 'id'):
            qs = qs.filter(tour_operator=tour_operator)

    pilgrim = filters.get('pilgrim')
    if pilgrim:
        if isinstance(pilgrim, int) or (isinstance(pilgrim, str) and pilgrim.isdigit()):
            qs = qs.filter(pilgrim_id=int(pilgrim))
        elif hasattr(pilgrim, 'id'):
            qs = qs.filter(pilgrim=pilgrim)

    ceremony_event = filters.get('ceremony_event')
    if ceremony_event:
        if isinstance(ceremony_event, int) or (isinstance(ceremony_event, str) and ceremony_event.isdigit()):
            qs = qs.filter(ceremony_event_id=int(ceremony_event))
        elif hasattr(ceremony_event, 'id'):
            qs = qs.filter(ceremony_event=ceremony_event)

    ceremony_venue = filters.get('ceremony_venue')
    if ceremony_venue:
        if isinstance(ceremony_venue, int) or (isinstance(ceremony_venue, str) and ceremony_venue.isdigit()):
            qs = qs.filter(ceremony_venue_id=int(ceremony_venue))
        elif hasattr(ceremony_venue, 'id'):
            qs = qs.filter(ceremony_venue=ceremony_venue)

    search = filters.get('search')
    if search:
        search = search.strip()
        qs = qs.filter(
            Q(transaction_number__icontains=search) |
            Q(description__icontains=search) |
            Q(account_head__name__icontains=search) |
            Q(sub_head__name__icontains=search)
        )

    qs = qs.select_related(
        'account_head', 'major_head', 'sub_head',
        'unit', 'internal_section', 'cohort', 'package',
        'tour_operator', 'pilgrim', 'ceremony_event', 'ceremony_venue'
    ).prefetch_related('transaction_units', 'transaction_sections').order_by('transaction_date', 'transaction_number')

    rows = []
    for tx in qs:
        sf_name = tx.major_head.name if tx.major_head else (tx.account_head.major_head.name if tx.account_head and tx.account_head.major_head else '—')
        ah_name = tx.account_head.name if tx.account_head else '—'
        sh_name = tx.sub_head.name if tx.sub_head else '—'
        tx_code = tx.transaction_number if tx.transaction_number else f"TX-{str(tx.pk)[:8]}"
        rows.append({
            'date': tx.transaction_date,
            'tx_id': tx_code,
            'direction': tx.direction,
            'description': tx.description or '—',
            'amount': tx.amount,
            'account_head': ah_name,
            'major_head': sf_name,
            'sub_head': sh_name,
            'pass_through': tx.pass_through,
            'unit': tx.unit.name if tx.unit else (', '.join(u.name for u in tx.transaction_units.all()) if tx.transaction_units.all() else '—'),
            'internal_section': tx.internal_section.name if tx.internal_section else (', '.join(s.name for s in tx.transaction_sections.all()) if tx.transaction_sections.all() else '—'),
            'cohort': tx.cohort.name if tx.cohort else '—',
            'package': tx.package.package_name if tx.package else '—',
            'tour_operator': tx.tour_operator.name if tx.tour_operator else '—',
            'pilgrim': str(tx.pilgrim) if tx.pilgrim else '—',
            'ceremony_event': tx.ceremony_event.name if tx.ceremony_event else '—',
            'ceremony_venue': tx.ceremony_venue.name if tx.ceremony_venue else '—',
        })
    return rows


registry.register(ReportDefinition(
    slug='dynamic-transactions',
    title='Dynamic Txns Statement',
    description='Dynamic Txn statement filtered by date range, dir (Inflow/Outflow), Sub Fund, Acct Head, Sub Head, Units, Secs, and Event/Pilgrim details',
    builder_func=build_dynamic_transactions,
    columns=[
        {'key': 'date', 'label': 'Date'},
        {'key': 'tx_id', 'label': 'Txn ID'},
        {'key': 'description', 'label': 'Description & Type'},
        {'key': 'account_head', 'label': 'Acct Head'},
        {'key': 'amount', 'label': 'Amount'},
        {'key': 'unit', 'label': 'Unit'},
        {'key': 'internal_section', 'label': 'Internal Sec'},
        {'key': 'cohort', 'label': 'Cohort'},
        {'key': 'package', 'label': 'Package'},
        {'key': 'tour_operator', 'label': 'Tour Operator'},
        {'key': 'pilgrim', 'label': 'Pilgrim'},
        {'key': 'ceremony_event', 'label': 'Event'},
        {'key': 'ceremony_venue', 'label': 'Venue'},
    ],
    supported_filters=[
        'account', 'financial_year', 'start_date', 'end_date', 'direction',
        'major_head', 'account_head', 'sub_head',
        'unit', 'internal_section', 'cohort', 'package', 'tour_operator', 'pilgrim',
        'ceremony_event', 'ceremony_venue'
    ],
    totals=['amount'],
    display_in_millions=False,
))
