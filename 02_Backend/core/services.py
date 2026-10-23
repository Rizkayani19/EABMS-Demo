from decimal import Decimal, InvalidOperation
from django.conf import settings
from django.db.models import Sum

from .models import AuditLog, Account, FinancialYear, BudgetLine
from .budget_inflow_models import BudgetInflowLine


def log_audit_action(actor, action, instance, old_values=None, new_values=None, account=None, ip_address=None):
    model_name = instance.__class__.__name__
    record_id = str(instance.pk or 'new')
    record_repr = str(instance)[:255]
    if account is None and hasattr(instance, 'account'): account = getattr(instance, 'account')
    AuditLog.objects.create(actor=actor if actor and actor.is_authenticated else None, account=account, action=action.upper(), model_name=model_name, record_id=record_id, record_repr=record_repr, old_values=old_values, new_values=new_values, ip_address=ip_address)


def get_active_account(request):
    account_id=request.session.get('active_account_id'); account=None
    if account_id:
        try: account=Account.objects.get(pk=account_id,is_active=True)
        except Account.DoesNotExist: account=None
    if not account:
        fund_code=getattr(settings,'ABMS_FUND','NGL'); account=Account.objects.filter(code__iexact=fund_code,is_active=True).first() or Account.objects.filter(is_active=True).first()
        if account: request.session['active_account_id']=account.id
    return account


def get_active_fy(request):
    fy_id=request.session.get('active_fy_id'); fy=None
    if fy_id:
        try: fy=FinancialYear.objects.get(pk=fy_id)
        except FinancialYear.DoesNotExist: fy=None
    if not fy:
        fy=FinancialYear.objects.filter(code='2026-27').first() or FinancialYear.objects.filter(status=FinancialYear.Status.OPEN).first()
        if fy: request.session['active_fy_id']=fy.id
    return fy


def _tx_queryset(account, financial_year, direction=None, start_date=None, end_date=None, pass_through=None):
    from .models import Transaction
    qs=Transaction.objects.filter(account=account,financial_year=financial_year,status=Transaction.Status.ACTIVE)
    if direction: qs=qs.filter(direction=direction)
    if start_date: qs=qs.filter(transaction_date__gte=start_date)
    if end_date: qs=qs.filter(transaction_date__lte=end_date)
    if pass_through is not None: qs=qs.filter(pass_through=pass_through)
    return qs


def get_total_actual_inflows(account, financial_year, start_date=None, end_date=None):
    from .models import Transaction
    return _tx_queryset(account,financial_year,Transaction.Direction.INFLOW,start_date,end_date).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

def get_total_actual_outflows(account, financial_year, start_date=None, end_date=None):
    from .models import Transaction
    return _tx_queryset(account,financial_year,Transaction.Direction.OUTFLOW,start_date,end_date).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

def get_total_pass_through(account, financial_year, start_date=None, end_date=None): return get_pass_through_outflows(account,financial_year,start_date,end_date)
def get_pass_through_inflows(account, financial_year, start_date=None, end_date=None):
    from .models import Transaction
    return _tx_queryset(account,financial_year,Transaction.Direction.INFLOW,start_date,end_date,True).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
def get_pass_through_outflows(account, financial_year, start_date=None, end_date=None):
    from .models import Transaction
    return _tx_queryset(account,financial_year,Transaction.Direction.OUTFLOW,start_date,end_date,True).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
def get_total_net_outflows(account, financial_year, start_date=None, end_date=None):
    from .models import Transaction
    return _tx_queryset(account,financial_year,Transaction.Direction.OUTFLOW,start_date,end_date).filter(pass_through=False).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
def get_opening_balance(account, financial_year):
    from .models import OpeningBalance
    return OpeningBalance.objects.filter(account=account,financial_year=financial_year).aggregate(t=Sum('balance_amount'))['t'] or Decimal('0.00')
def get_balance_available(account, financial_year): return get_opening_balance(account,financial_year)+get_total_actual_inflows(account,financial_year)-get_total_actual_outflows(account,financial_year)

def get_approved_budget_position(account, financial_year):
    outflow=BudgetLine.objects.filter(budget__account=account,budget__financial_year=financial_year,budget__status='APPROVED').aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
    inflow=BudgetInflowLine.objects.filter(budget__account=account,budget__financial_year=financial_year,budget__status='APPROVED').aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
    return {'approved_outflow_budget':outflow,'approved_inflow_budget':inflow,'approved_net_budget':inflow-outflow}
def get_total_approved_budget(account, financial_year): return get_approved_budget_position(account,financial_year)['approved_outflow_budget']
def get_total_approved_inflow_budget(account, financial_year): return get_approved_budget_position(account,financial_year)['approved_inflow_budget']

def get_budget_consumed(account, financial_year, account_head=None, unit=None, start_date=None, end_date=None):
    from .models import Transaction
    from django.db.models import Q
    qs=_tx_queryset(account,financial_year,Transaction.Direction.OUTFLOW,start_date,end_date,False)
    if account_head: qs=qs.filter(account_head=account_head)
    if unit: qs=qs.filter(Q(unit=unit)|Q(transaction_units=unit)).distinct()
    return qs.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
def get_inflow_budget_consumed(account, financial_year, account_head=None, unit=None, start_date=None, end_date=None):
    from .models import Transaction
    qs=_tx_queryset(account,financial_year,Transaction.Direction.INFLOW,start_date,end_date)
    if account_head: qs=qs.filter(account_head=account_head)
    if unit: qs=qs.filter(unit=unit)
    return qs.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
def get_balance_of_budget(account, financial_year): return get_total_approved_budget(account,financial_year)-get_budget_consumed(account,financial_year)
def get_inflow_budget_balance(account, financial_year): return get_total_approved_inflow_budget(account,financial_year)-get_inflow_budget_consumed(account,financial_year)
def get_net_budget_balance(account, financial_year):
    p=get_approved_budget_position(account,financial_year); return p['approved_net_budget']-(get_inflow_budget_consumed(account,financial_year)-get_budget_consumed(account,financial_year))
def get_budget_utilisation(account, financial_year):
    b=get_total_approved_budget(account,financial_year); c=get_budget_consumed(account,financial_year); return c/b*Decimal('100') if b else None
def get_inflow_budget_utilisation(account, financial_year):
    b=get_total_approved_inflow_budget(account,financial_year); c=get_inflow_budget_consumed(account,financial_year); return c/b*Decimal('100') if b else None
def is_over_budget(account, financial_year):
    b=get_total_approved_budget(account,financial_year); return bool(b and get_budget_consumed(account,financial_year)>b)
def get_reimbursement_summary(account, financial_year):
    from .models import Reimbursement
    v=Reimbursement.objects.filter(original_outflow__account=account,original_outflow__financial_year=financial_year).aggregate(expected=Sum('expected_amount'),received=Sum('received_amount'))
    e=v['expected'] or Decimal('0.00'); r=v['received'] or Decimal('0.00'); return {'expected':e,'received':r,'pending':e-r}
def get_period_summary(account, financial_year, start_date, end_date=None):
    i=get_total_actual_inflows(account,financial_year,start_date,end_date); o=get_total_actual_outflows(account,financial_year,start_date,end_date); ob=get_opening_balance(account,financial_year); return {'period_opening_balance':ob,'period_inflows':i,'period_outflows':o,'period_closing_balance':ob+i-o}

def _resolve_sub_fund_opening_from_breakdown(mh, bk):
    """
    Robust resolver for sub-fund opening balance from breakdown dict.
    Supports matching by:
      1. str(mh.id)
      2. mh.code
      3. mh.name
      4. Normalized case-insensitive name
      5. Explicit fund aliases (e.g. Canteen Sub-Fund vs Staff cafeteria Fund)
    """
    if not bk:
        return None
    for k in (str(mh.id), mh.code, mh.name):
        if k and k in bk:
            try:
                return Decimal(str(bk[k]))
            except (ValueError, InvalidOperation):
                pass
    norm_name = mh.name.strip().lower()
    norm_code = mh.code.strip().lower() if mh.code else ''
    for b_key, b_val in bk.items():
        k_clean = b_key.strip().lower()
        if k_clean == norm_name or (norm_code and k_clean == norm_code):
            try:
                return Decimal(str(b_val))
            except (ValueError, InvalidOperation):
                pass
    aliases = {
        'CANT-SF': ['canteen sub-fund', 'canteen sub fund', 'staff cafeteria fund', 'cafeteria fund', 'staff cafeteria'],
        'ACAD-SF': ['academy canteen sub fund', 'academy canteen sub-fund', 'academy canteen'],
        'SHB-SF': ['staff handbook sub-fund', 'staff handbook', 'hand book'],
        'BG-SF': ['bank guarantee staff sub-fund', 'bank guarantee staff', 'bank guarantee'],
        'L-SF': ['loan sub fund', 'loan sub-fund', 'loan'],
        'ORNT-SF': ['office rent'],
        'STP-SF': ['staff petition-sf', 'staff petition'],
        'NGL-SF': ['ngl sub-fund', 'ngl sub fund', 'ngl'],
    }
    for target in aliases.get(mh.code, []):
        for b_key, b_val in bk.items():
            if b_key.strip().lower() == target:
                try:
                    return Decimal(str(b_val))
                except (ValueError, InvalidOperation):
                    pass
    return None


def get_sub_fund_distribution_summary(account, financial_year):
    from .models import MajorHead, Transaction, OpeningBalance, AccountHead
    from masters.views import _extract_sub_fund_breakdown
    if not account or not financial_year: return {'sub_funds':[],'totals':{},'fund_balance_available':Decimal('0.00'),'variance':Decimal('0.00'),'is_reconciled':True,'has_sub_fund_opening_breakdown':False,'transfers_history':[]}
    mhs=list(MajorHead.objects.filter(account=account,is_active=True).order_by('display_order','id')) or list(MajorHead.objects.filter(account=account).order_by('display_order','id'))
    ob=OpeningBalance.objects.filter(account=account,financial_year=financial_year).first(); total_ob=ob.balance_amount if ob else Decimal('0.00'); bk=_extract_sub_fund_breakdown(ob.remarks) if ob else {}
    primary=None
    if not bk and mhs:
        for mh in mhs:
            if account.code.lower() in mh.code.lower() or account.code.lower() in mh.name.lower(): primary=mh.id; break
        if primary is None: primary=mhs[0].id
    sub_funds=[]; tot_opening=tot_in_op=tot_in_pt=tot_in=tot_out_op=tot_out_pt=tot_out=tot_net=Decimal('0.00'); fund_balance=get_balance_available(account,financial_year)
    for mh in mhs:
        sub_ob = _resolve_sub_fund_opening_from_breakdown(mh, bk)
        if sub_ob is None:
            if not bk and mh.id == primary:
                sub_ob = total_ob
            else:
                sub_ob = Decimal('0.00')
        txs=Transaction.objects.filter(account=account,financial_year=financial_year,major_head=mh,status=Transaction.Status.ACTIVE)
        io=txs.filter(direction=Transaction.Direction.INFLOW,pass_through=False).aggregate(s=Sum('amount'))['s'] or Decimal('0.00'); ip=txs.filter(direction=Transaction.Direction.INFLOW,pass_through=True).aggregate(s=Sum('amount'))['s'] or Decimal('0.00'); oo=txs.filter(direction=Transaction.Direction.OUTFLOW,pass_through=False).aggregate(s=Sum('amount'))['s'] or Decimal('0.00'); op=txs.filter(direction=Transaction.Direction.OUTFLOW,pass_through=True).aggregate(s=Sum('amount'))['s'] or Decimal('0.00'); si=io+ip; so=oo+op; nb=sub_ob+si-so
        tot_opening+=sub_ob; tot_in_op+=io; tot_in_pt+=ip; tot_in+=si; tot_out_op+=oo; tot_out_pt+=op; tot_out+=so; tot_net+=nb
        ah=AccountHead.objects.filter(account=account,major_head=mh,is_active=True).order_by('display_order','id').first(); sub_funds.append({'major_head':mh,'id':mh.id,'name':mh.name,'code':mh.code,'opening_balance':sub_ob,'operational_inflows':io,'pass_through_inflows':ip,'total_inflows':si,'operational_outflows':oo,'pass_through_outflows':op,'total_outflows':so,'net_balance':nb,'is_deficit':nb<0,'default_account_head_id':ah.id if ah else '','first_account_head_name':ah.name if ah else ''})
    for sf in sub_funds: sf['share_pct']=(sf['net_balance']/tot_net*Decimal('100')).quantize(Decimal('0.1')) if tot_net>0 and sf['net_balance']>0 else Decimal('0.0')
    transfer_txs=Transaction.objects.filter(account=account,financial_year=financial_year,pass_through=True,status=Transaction.Status.ACTIVE).select_related('major_head','account_head','sub_head','created_by').order_by('-transaction_date','-created_at')[:30]
    variance=(tot_net-fund_balance).quantize(Decimal('0.01'))
    return {'sub_funds':sub_funds,'totals':{'opening_balance':tot_opening,'operational_inflows':tot_in_op,'pass_through_inflows':tot_in_pt,'total_inflows':tot_in,'operational_outflows':tot_out_op,'pass_through_outflows':tot_out_pt,'total_outflows':tot_out,'net_balance':tot_net},'fund_balance_available':fund_balance,'variance':variance,'is_reconciled':variance==Decimal('0.00'),'has_sub_fund_opening_breakdown':bool(bk),'transfers_history':transfer_txs}
