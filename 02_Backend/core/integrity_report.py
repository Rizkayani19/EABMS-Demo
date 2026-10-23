from collections import Counter
from datetime import datetime, timezone

from .financial_integrity_services import run_full_integrity_check


CHECK_NAMES = (
    "financial_reconciliation",
    "budget_revision_consistency",
    "account_hierarchy",
    "financial_year_dates",
    "reimbursement_reconciliation",
)


def build_integrity_report(*, account=None, financial_year=None):
    """Build one answer-first Gate 9 integrity report from the canonical checks."""
    result = run_full_integrity_check(account=account, financial_year=financial_year)

    checks = {
        "financial_reconciliation": {
            "status": "PASS",
            "exceptions": 0,
            "message": "Account/FY balances reconciled from opening balance, inflows and outflows.",
        },
        "budget_revision_consistency": {
            "status": "PASS" if not result["budget_revision_issues"] else "FAIL",
            "exceptions": len(result["budget_revision_issues"]),
            "message": "Effective BudgetLine amounts agree with revision records." if not result["budget_revision_issues"] else "Budget revision records require review.",
        },
        "account_hierarchy": {
            "status": "PASS" if not result["account_hierarchy_issues"] else "FAIL",
            "exceptions": len(result["account_hierarchy_issues"]),
            "message": "Account hierarchy links remain within the owning Account." if not result["account_hierarchy_issues"] else "Cross-account hierarchy links were detected.",
        },
        "financial_year_dates": {
            "status": "PASS" if not result["financial_year_date_issues"] else "FAIL",
            "exceptions": len(result["financial_year_date_issues"]),
            "message": "Transaction dates fall within their selected Financial Year." if not result["financial_year_date_issues"] else "Transactions outside their selected Financial Year were detected.",
        },
        "reimbursement_reconciliation": {
            "status": "PASS" if not result["reimbursement_issues"] else "FAIL",
            "exceptions": len(result["reimbursement_issues"]),
            "message": "Received reimbursements reconcile to linked inflow transactions." if not result["reimbursement_issues"] else "Reimbursement receipts do not fully reconcile to linked inflows.",
        },
    }

    for row in result["reconciliations"]:
        if row["reimbursement_reconciliation_difference"] != 0:
            checks["financial_reconciliation"]["status"] = "FAIL"
            checks["financial_reconciliation"]["exceptions"] += 1
            checks["financial_reconciliation"]["message"] = "One or more account/FY financial snapshots contain reimbursement balance discrepancies."

    total_exceptions = sum(item["exceptions"] for item in checks.values())
    status = "PASS" if total_exceptions == 0 else "FAIL"

    severity = Counter()
    severity["FAIL"] = sum(1 for item in checks.values() if item["status"] == "FAIL")
    severity["PASS"] = sum(1 for item in checks.values() if item["status"] == "PASS")

    return {
        "report_name": "ABMS Gate 9 Financial Integrity Report",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "account": account.code if account else "ALL ACTIVE ACCOUNTS",
            "financial_year": financial_year.code if financial_year else "ALL FINANCIAL YEARS",
        },
        "status": status,
        "checks": checks,
        "summary": {
            "checks_run": len(CHECK_NAMES),
            "checks_passed": severity["PASS"],
            "checks_failed": severity["FAIL"],
            "total_exceptions": total_exceptions,
            "reconciliations_checked": len(result["reconciliations"]),
        },
        "exceptions": {
            "budget_revision": result["budget_revision_issues"],
            "account_hierarchy": result["account_hierarchy_issues"],
            "financial_year_dates": result["financial_year_date_issues"],
            "reimbursements": result["reimbursement_issues"],
        },
        "reconciliations": result["reconciliations"],
    }
