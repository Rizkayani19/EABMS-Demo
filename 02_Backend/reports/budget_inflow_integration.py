from decimal import Decimal
from core.models import Transaction, Budget, BudgetLine
from core.budget_inflow_models import BudgetInflowLine
from .registry import registry, ReportDefinition


def build_budget_position(filters):
    account, fy = filters.get('account'), filters.get('financial_year')
    if not account or not fy: return []
    rows={}
    def row_for(key, name):
        return rows.setdefault(key, {'account_head':name,'approved_inflow_budget':Decimal('0.00'),'actual_inflows':Decimal('0.00'),'inflow_balance':Decimal('0.00'),'inflow_utilisation_pct':None,'approved_outflow_budget':Decimal('0.00'),'actual_outflows':Decimal('0.00'),'outflow_balance':Decimal('0.00'),'outflow_utilisation_pct':None,'net_budget_position':Decimal('0.00')})
    for line in BudgetInflowLine.objects.filter(budget__account=account,budget__financial_year=fy,budget__status=Budget.Status.APPROVED).select_related('account_head'):
        row_for(line.account_head_id,line.account_head.name)['approved_inflow_budget'] += line.amount
    for line in BudgetLine.objects.filter(budget__account=account,budget__financial_year=fy,budget__status=Budget.Status.APPROVED).select_related('account_head'):
        row_for(line.account_head_id,line.account_head.name)['approved_outflow_budget'] += line.amount
    for tx in Transaction.objects.filter(account=account,financial_year=fy,status=Transaction.Status.ACTIVE,pass_through=False).select_related('account_head'):
        key=tx.account_head_id; row=row_for(key,tx.account_head.name if tx.account_head else 'Other')
        if tx.direction==Transaction.Direction.INFLOW: row['actual_inflows'] += tx.amount
        else: row['actual_outflows'] += tx.amount
    for row in rows.values():
        row['inflow_balance']=row['approved_inflow_budget']-row['actual_inflows']; row['outflow_balance']=row['approved_outflow_budget']-row['actual_outflows']
        row['inflow_utilisation_pct']=row['actual_inflows']/row['approved_inflow_budget']*Decimal('100') if row['approved_inflow_budget'] else None
        row['outflow_utilisation_pct']=row['actual_outflows']/row['approved_outflow_budget']*Decimal('100') if row['approved_outflow_budget'] else None
        row['net_budget_position']=row['inflow_balance']-row['outflow_balance']
    return sorted(rows.values(),key=lambda x:x['account_head'])


registry.register(ReportDefinition(slug='budget-position',title='Budget Position — Inflows & Outflows',description='Approved inflow and outflow budgets compared with actual inflows and outflows.',builder_func=build_budget_position,columns=[{'key':'account_head','label':'Account Head'},{'key':'approved_inflow_budget','label':'Approved Inflow Budget'},{'key':'actual_inflows','label':'Actual Inflows'},{'key':'inflow_balance','label':'Inflow Balance'},{'key':'inflow_utilisation_pct','label':'Inflow Util %'},{'key':'approved_outflow_budget','label':'Approved Outflow Budget'},{'key':'actual_outflows','label':'Actual Outflows'},{'key':'outflow_balance','label':'Outflow Balance'},{'key':'outflow_utilisation_pct','label':'Outflow Util %'},{'key':'net_budget_position','label':'Net Budget Position'}],supported_filters=['start_date','end_date','major_head','account_head','sub_head','unit_ids'],totals=['approved_inflow_budget','actual_inflows','inflow_balance','approved_outflow_budget','actual_outflows','outflow_balance','net_budget_position'],export_supported=True,display_in_millions=True))
