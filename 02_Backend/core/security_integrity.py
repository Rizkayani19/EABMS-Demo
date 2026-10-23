from decimal import Decimal

from .models import AuditLog, OpeningBalance, Reimbursement, Transaction


def find_transactions_without_audit_log(account=None, financial_year=None):
    qs = Transaction.objects.all()
    if account is not None:
        qs = qs.filter(account=account)
    if financial_year is not None:
        qs = qs.filter(financial_year=financial_year)

    audited_ids = set(
        AuditLog.objects.filter(model_name="Transaction")
        .values_list("record_id", flat=True)
    )
    return [
        {
            "transaction_id": str(tx.id),
            "transaction_number": tx.transaction_number,
            "account": tx.account.code,
            "financial_year": tx.financial_year.code,
        }
        for tx in qs
        if str(tx.id) not in audited_ids
    ]


def find_reimbursement_link_issues(account=None, financial_year=None):
    qs = Reimbursement.objects.select_related(
        "original_outflow__account",
        "original_outflow__financial_year",
        "received_inflow__account",
        "received_inflow__financial_year",
    ).all()
    if account is not None:
        qs = qs.filter(original_outflow__account=account)
    if financial_year is not None:
        qs = qs.filter(original_outflow__financial_year=financial_year)

    issues = []
    for reimbursement in qs:
        received = reimbursement.received_amount or Decimal("0.00")
        if received > 0 and reimbursement.received_inflow is None:
            issues.append({
                "reimbursement_id": str(reimbursement.id),
                "issue": "received amount has no linked inflow transaction",
            })
            continue
        if reimbursement.received_inflow:
            inflow = reimbursement.received_inflow
            original = reimbursement.original_outflow
            if inflow.direction != Transaction.Direction.INFLOW:
                issues.append({"reimbursement_id": str(reimbursement.id), "issue": "linked transaction is not an inflow"})
            if original and inflow.account_id != original.account_id:
                issues.append({"reimbursement_id": str(reimbursement.id), "issue": "received inflow crosses account boundary"})
            if original and inflow.financial_year_id != original.financial_year_id:
                issues.append({"reimbursement_id": str(reimbursement.id), "issue": "received inflow crosses financial year boundary"})
            if inflow.amount != received:
                issues.append({"reimbursement_id": str(reimbursement.id), "issue": "linked inflow amount does not match received amount"})
    return issues


def find_opening_balance_confirmation_issues(account=None, financial_year=None):
    qs = OpeningBalance.objects.all()
    if account is not None:
        qs = qs.filter(account=account)
    if financial_year is not None:
        qs = qs.filter(financial_year=financial_year)

    issues = []
    for opening in qs:
        if opening.is_confirmed and (opening.confirmed_by_id is None or opening.confirmed_at is None):
            issues.append({
                "opening_balance_id": opening.id,
                "issue": "confirmed opening balance lacks confirmation metadata",
            })
    return issues


def run_security_integrity_check(account=None, financial_year=None):
    transaction_issues = find_transactions_without_audit_log(account, financial_year)
    reimbursement_issues = find_reimbursement_link_issues(account, financial_year)
    opening_issues = find_opening_balance_confirmation_issues(account, financial_year)

    return {
        "status": "PASS" if not (transaction_issues or reimbursement_issues or opening_issues) else "FAIL",
        "transaction_audit_issues": transaction_issues,
        "reimbursement_link_issues": reimbursement_issues,
        "opening_balance_confirmation_issues": opening_issues,
        "total_exceptions": len(transaction_issues) + len(reimbursement_issues) + len(opening_issues),
    }
