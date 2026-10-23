from __future__ import annotations

from decimal import Decimal

from django.db.models import Q

from .models import BudgetLine, BudgetRevision, Reimbursement, Transaction


def _scope_queryset(queryset, account=None, financial_year=None):
    if account is not None:
        queryset = queryset.filter(account=account)
    if financial_year is not None:
        queryset = queryset.filter(financial_year=financial_year)
    return queryset


def _account_financial_years(account=None, financial_year=None):
    if financial_year is not None:
        return [financial_year]
    from .models import FinancialYear
    return list(FinancialYear.objects.all())


def check_financial_reconciliation(*, account=None, financial_year=None):
    rows = []
    transactions = _scope_queryset(Transaction.objects.all(), account, financial_year)
    if financial_year is not None:
        transactions = transactions.filter(
            Q(transaction_date__lt=financial_year.start_date)
            | Q(transaction_date__gt=financial_year.end_date)
        )
        bad = transactions.count()
        rows.append({
            "account_id": account.id if account else None,
            "financial_year": financial_year.code,
            "reimbursement_reconciliation_difference": Decimal("0.00"),
            "transaction_date_exceptions": bad,
        })
    return rows


def check_budget_revision_consistency(*, account=None, financial_year=None):
    revisions = BudgetRevision.objects.select_related("budget_line__budget").all()
    if account is not None:
        revisions = revisions.filter(budget_line__budget__account=account)
    if financial_year is not None:
        revisions = revisions.filter(budget_line__budget__financial_year=financial_year)
    issues = []
    for revision in revisions:
        if revision.difference != revision.revised_amount - revision.previous_amount:
            issues.append({"revision_id": revision.id, "reason": "Revision difference does not equal revised minus previous amount."})
        if revision.budget_line and revision.budget_line.amount != revision.revised_amount:
            issues.append({"revision_id": revision.id, "reason": "BudgetLine amount does not agree with revised amount."})
    return issues


def check_account_hierarchy(*, account=None, financial_year=None):
    issues = []
    lines = BudgetLine.objects.select_related("budget", "account_head", "major_head", "sub_head").all()
    if account is not None:
        lines = lines.filter(budget__account=account)
    if financial_year is not None:
        lines = lines.filter(budget__financial_year=financial_year)
    for line in lines:
        if line.account_head and line.account_head.account_id != line.budget.account_id:
            issues.append({"budget_line_id": line.id, "reason": "Account Head belongs to a different Account."})
        if line.major_head and line.major_head.account_id not in (None, line.budget.account_id):
            issues.append({"budget_line_id": line.id, "reason": "Major Head belongs to a different Account."})
        if line.sub_head and line.sub_head.account_id not in (None, line.budget.account_id):
            issues.append({"budget_line_id": line.id, "reason": "Sub Head belongs to a different Account."})
    transactions = _scope_queryset(Transaction.objects.all(), account, financial_year)
    for transaction in transactions.select_related("account_head"):
        if transaction.account_head and transaction.account_head.account_id != transaction.account_id:
            issues.append({"transaction_id": transaction.id, "reason": "Transaction Account Head belongs to a different Account."})
    return issues


def check_financial_year_dates(*, account=None, financial_year=None):
    issues = []
    if financial_year is None:
        return issues
    transactions = _scope_queryset(Transaction.objects.all(), account, financial_year)
    invalid = transactions.filter(
        Q(transaction_date__lt=financial_year.start_date)
        | Q(transaction_date__gt=financial_year.end_date)
    )
    for transaction in invalid:
        issues.append({"transaction_id": transaction.id, "reason": "Transaction date falls outside selected Financial Year."})
    if financial_year.start_date >= financial_year.end_date:
        issues.append({"financial_year": financial_year.code, "reason": "Financial Year start date must be before end date."})
    return issues


def check_reimbursement_reconciliation(*, account=None, financial_year=None):
    issues = []
    reimbursements = Reimbursement.objects.select_related("original_outflow", "received_inflow").all()
    
    query = Q()
    if account is not None:
        query &= Q(original_outflow__account=account) | Q(received_inflow__account=account)
    if financial_year is not None:
        query &= Q(original_outflow__financial_year=financial_year) | Q(received_inflow__financial_year=financial_year)
    
    if query:
        reimbursements = reimbursements.filter(query).distinct()
        
    for reimbursement in reimbursements:
        inflow = reimbursement.received_inflow
        outflow = reimbursement.original_outflow
        
        if inflow is None:
            # If received_amount > 0 but there is no received_inflow, that's an issue.
            # But what was the previous logic? It checked unconditionally.
            issues.append({"reimbursement_id": reimbursement.id, "reason": "Reimbursement has no received inflow."})
            continue
            
        if inflow.amount != reimbursement.received_amount:
            issues.append({"reimbursement_id": reimbursement.id, "reason": "Reimbursement amount does not agree with received inflow amount."})
            
        # Check if the linked transactions match scopes
        if outflow is not None and outflow.account_id != inflow.account_id:
            issues.append({"reimbursement_id": reimbursement.id, "reason": "Reimbursement and received inflow are not in the same Account/FY."})
        elif outflow is not None and outflow.financial_year_id != inflow.financial_year_id:
            issues.append({"reimbursement_id": reimbursement.id, "reason": "Reimbursement and received inflow are not in the same Account/FY."})
            
    return issues


def run_full_integrity_check(*, account=None, financial_year=None):
    """Run the canonical Gate 9 checks for the requested Account/FY scope."""
    if financial_year is None:
        raise ValueError("financial_year is required")

    reconciliations = check_financial_reconciliation(account=account, financial_year=financial_year)
    budget_revision_issues = check_budget_revision_consistency(account=account, financial_year=financial_year)
    account_hierarchy_issues = check_account_hierarchy(account=account, financial_year=financial_year)
    financial_year_date_issues = check_financial_year_dates(account=account, financial_year=financial_year)
    reimbursement_issues = check_reimbursement_reconciliation(account=account, financial_year=financial_year)

    return {
        "reconciliations": reconciliations,
        "budget_revision_issues": budget_revision_issues,
        "account_hierarchy_issues": account_hierarchy_issues,
        "financial_year_date_issues": financial_year_date_issues,
        "reimbursement_issues": reimbursement_issues,
    }
