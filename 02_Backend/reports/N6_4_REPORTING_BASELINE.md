# ABMS N6.4 — Reporting Controls & Validation Baseline

**Status:** Working implementation baseline

## Purpose

N6.4 consolidates the reporting-control requirements already approved for ABMS. The transaction ledger remains the Single Source of Truth; every screen, Excel workbook, PDF and CSV report must derive from the same filtered transaction dataset.

## Approved Reporting Dimensions

Reports must support, where applicable:

- Account
- Financial Year
- From Date / To Date
- Inflow / Outflow
- Account Head
- Sub Head
- Transaction Nature
- Budget Type
- Unit(s)
- Internal Section(s)
- Transaction Type
- Status
- Import Batch

Unit and Internal Section are independent configurable Masters. They are not hard-coded reporting categories.

## Organisational Filtering

Unit and Internal Section filters support:

- All
- Single selection
- Multiple selection
- Combined Unit + Section analysis

A transaction may legitimately involve multiple Units and/or multiple Internal Sections. A Unit normally has a responsible Internal Section, but this is not mandatory. A Unit may be managed by multiple Sections.

Where allocation records exist, organisational reports must use the allocation-aware amount so multi-Unit/multi-Section transactions are not incorrectly double-counted.

## Current Organisational Rules

- ACAD → Unit = ACAD; normally managed by EVT.
- Security-unit transactions → normally Section = Security; actual Security Unit should also be recorded where identifiable.
- Coordination is an Internal Section responsible for HR management, inter-section management and coordination, coordination of the CEO activities/programmes, private accounts, security, administration and related coordination matters.

## Report Date Basis

Transaction-based reports use the transaction date. Date filters are inclusive and must reject an end date earlier than the start date.

## Giant Management Workbook

The preferred management export is `ABMS_Management_Report.xlsx`.

Required architecture:

1. Executive Summary
2. Report Parameters
3. Master Transactions — one row per authoritative transaction
4. Inflows
5. Outflows
6. Monthly Summary
7. Account Head Summary
8. Sub Head Summary
9. Unit Summary
10. Section Summary
11. Unit-Section Analysis
12. Budget vs Actual
13. Reimbursements
14. Audit / Import Summary
15. Deleted Transactions where authorised

The Master Transactions sheet is the exported Single Source of Truth. All other sheets are analytical/reporting views and must not contain independently maintained financial figures.

## Export Consistency

The exact filters selected in the web Report Center must propagate to Excel, PDF and CSV exports. Every generated report must display its filter context, including Account, FY, date range, selected Units and selected Internal Sections.

## Current Code Baseline

The existing reporting view already:

- reads active Account/FY context from the session;
- validates report dates;
- accepts multiple Unit IDs and Internal Section IDs;
- validates selected organisational IDs against active Masters;
- exposes Unit and Internal Section choices to the Report Center;
- supports individual PDF/Excel and Giant Management Workbook exports;
- uses allocation-aware reporting messaging for organisational reports.

The Report Center currently exposes the available report registry and the report view provides multi-select Unit/Section filters and the three export paths.

## N6.4 Acceptance Criteria

1. No report stores independent financial totals.
2. Web and export outputs use the same filter object and underlying dataset.
3. Unit and Section multi-selection works consistently.
4. Blank Unit/Section selection means All, subject to the report's supported filters.
5. Date validation is consistent across all report formats.
6. Exported reports identify their filter context.
7. Multi-organisational transactions are not double-counted in organisational summaries.
8. Inactive Masters remain usable for historical transaction attribution but are not offered as normal active filter choices unless specifically required for historical/audit reporting.
9. The Giant Management Workbook contains the complete filtered Master Transactions dataset and derived report sheets.
10. Any future Unit or Section automatically becomes reportable without code changes to the reporting engine.

## Next Step

After N6.4 validation, proceed to N6.5: comprehensive reporting QA/regression tests, followed by the Future Budget / Existing Budget Analysis reporting module using the same transaction and budget Single Source of Truth architecture.
