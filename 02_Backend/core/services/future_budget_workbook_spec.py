"""Future Budget Management Workbook specification.

This module documents the authoritative workbook contract. The workbook is an
export/view of ABMS data; it is never a second source of truth.
"""

WORKBOOK_SHEETS = [
    "01 Cover & Parameters",
    "02 Executive Summary",
    "03 Existing Budget vs Actual",
    "04 Head-wise Analysis",
    "05 System Suggested",
    "06 Management Proposed",
    "07 Approved Budget",
    "08 Management Requirements",
    "09 Unit-wise Analysis",
    "10 Internal Section Analysis",
    "11 Unit-Section Analysis",
    "12 Personnel Effect",
    "13 Known Changes",
    "14 One-Time-Deducted",
    "15 Variance & Decision Flags",
    "16 Audit & Approval",
]

# Every analytical sheet must be generated from the same filtered planning
# dataset and carry the selected account/FY/date/unit/section parameters.
EXPORT_RULES = {
    "source_of_truth": "ABMS database transaction and future-budget planning records",
    "master_transaction_sheet": True,
    "filter_context_required": True,
    "include_unit_filters": True,
    "include_internal_section_filters": True,
    "preserve_system_suggested": True,
    "preserve_management_proposed": True,
    "preserve_approved": True,
}
