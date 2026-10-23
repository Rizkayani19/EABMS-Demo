from datetime import datetime
from decimal import Decimal

from django.db.models import Sum
from django.shortcuts import render
from django.http import HttpResponse, Http404
from django.contrib.auth.decorators import login_required

from .registry import registry
from . import services
from . import date_integrity  # noqa: F401 - replaces date-sensitive registry builders
from . import organisational  # noqa: F401 - registers unit/section reports
from . import present_balance_reports  # noqa: F401 - registers present balance reports
from .exporters.pdf import export_to_pdf
from .exporters.excel import export_to_excel
from .exporters.management_workbook import export_management_workbook
from core.models import Transaction, Account, FinancialYear, Unit, InternalSection, MajorHead, AccountHead, SubHead
from core.services import get_total_pass_through, get_pass_through_inflows
from masters.models import Cohort, CohortPackage, TourOperator, Pilgrim, CeremonyEvent, CeremonyVenue


def _parse_report_date(value, field_name):
    if not value:
        return None, None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date(), None
    except (TypeError, ValueError):
        return None, f"{field_name} must be a valid date."


def _get_filters_from_request(request):
    filters = {}
    errors = []
    account_id = request.session.get("active_account_id")
    fy_id = request.session.get("active_fy_id")
    if account_id:
        filters["account"] = Account.objects.filter(pk=account_id).first()
    if not filters.get("account"):
        filters["account"] = getattr(request, "account", None) or Account.objects.filter(code="NGL").first() or Account.objects.first()

    raw_fy_ids = request.GET.getlist("fy_ids") or request.GET.getlist("financial_year")
    selected_fys = []
    if raw_fy_ids:
        f_ids = [int(x) for x in raw_fy_ids if str(x).strip().isdigit()]
        if f_ids:
            selected_fys = list(FinancialYear.objects.filter(pk__in=f_ids).order_by('start_date'))
    if not selected_fys and fy_id:
        default_fy = FinancialYear.objects.filter(pk=fy_id).first()
        if default_fy:
            selected_fys = [default_fy]
    if not selected_fys:
        req_fy = getattr(request, "fy", None) or FinancialYear.objects.filter(name__icontains="2025-26").first() or FinancialYear.objects.first()
        if req_fy:
            selected_fys = [req_fy]
    filters["selected_fys"] = selected_fys
    if selected_fys:
        filters["financial_year"] = selected_fys[0]

    start_raw = request.GET.get("start_date", "").strip()
    end_raw = request.GET.get("end_date", "").strip()
    start_date, error = _parse_report_date(start_raw, "Start Date")
    if error:
        errors.append(error)
    end_date, error = _parse_report_date(end_raw, "End Date")
    if error:
        errors.append(error)
    if start_date and end_date and start_date > end_date:
        errors.append("Start Date cannot be later than End Date.")
    else:
        if start_date:
            filters["start_date"] = start_date
        if end_date:
            filters["end_date"] = end_date
    filters["start_date_raw"] = start_raw
    filters["end_date_raw"] = end_raw

    for key in (
        "major_head", "sub_head", "account_head", "unit", "internal_section",
        "direction", "outflow_nature", "status", "search",
        "cohort", "package", "tour_operator", "pilgrim", "ceremony_event", "ceremony_venue"
    ):
        value = request.GET.get(key)
        if value:
            filters[key] = value

    raw_unit_ids = request.GET.getlist("unit_ids") or request.GET.getlist("unit")
    raw_section_ids = request.GET.getlist("internal_section_ids") or request.GET.getlist("internal_section")
    unit_ids = [int(v) for v in raw_unit_ids if str(v).strip().isdigit()]
    section_ids = [int(v) for v in raw_section_ids if str(v).strip().isdigit()]
    valid_units = set(Unit.objects.filter(pk__in=unit_ids).values_list("pk", flat=True))
    valid_sections = set(InternalSection.objects.filter(pk__in=section_ids).values_list("pk", flat=True))
    filters["unit_ids"] = [i for i in unit_ids if i in valid_units]
    filters["internal_section_ids"] = [i for i in section_ids if i in valid_sections]

    pass_through = request.GET.get("pass_through")
    if pass_through == "true":
        filters["pass_through"] = True
    elif pass_through == "false":
        filters["pass_through"] = False
    return filters, errors


def _trim_month_rows_to_selected_range(dataset, filters):
    if not dataset:
        return dataset
    start = filters.get("start_date")
    end = filters.get("end_date")
    if not start and not end:
        return dataset
    start_key = start.strftime("%Y-%m") if start else None
    end_key = end.strftime("%Y-%m") if end else None
    trimmed = []
    for row in dataset:
        month = row.get("month")
        if not isinstance(month, str) or len(month) != 7 or month[4] != "-":
            trimmed.append(row)
            continue
        if start_key and month < start_key:
            continue
        if end_key and month > end_key:
            continue
        trimmed.append(row)
    return trimmed


REPORT_CATEGORIES = {
    'dynamic-transactions': 'executive',
    'account-summary': 'executive',
    'fy-summary': 'executive',
    'monthly-trend': 'executive',
    'present-sub-fund-balance': 'executive',
    'present-account-head-balance': 'executive',
    'present-sub-account-head-balance': 'executive',
    'budget-vs-actual': 'budget',
    'yoy-comparative': 'budget',
    'budget-utilisation': 'budget',
    'routine-vs-addl': 'budget',
    'monthly-inflows': 'periodic',
    'monthly-outflows': 'periodic',
    'pass-through-summary': 'periodic',
    'account-head-summary': 'periodic',
    'sub-head-summary': 'periodic',
    'major-head-summary': 'periodic',
    'unit-summary': 'organisational',
    'internal-section-summary': 'organisational',
    'unit-section-summary': 'organisational',
    'organisational-transactions': 'organisational',
    'reimbursements': 'claims',
}

REPORT_PRIORITIES = [
    'present-sub-fund-balance',
    'present-account-head-balance',
    'present-sub-account-head-balance',
    'dynamic-transactions',
    'account-summary',
    'budget-vs-actual',
    'monthly-trend',
    'monthly-outflows',
    'monthly-inflows',
    'budget-utilisation',
    'major-head-summary',
    'account-head-summary',
    'yoy-comparative',
    'fy-summary',
    'unit-summary',
    'internal-section-summary',
    'routine-vs-addl',
    'sub-head-summary',
    'pass-through-summary',
    'unit-section-summary',
    'organisational-transactions',
    'reimbursements',
]


@login_required
def report_center(request):
    all_reports = registry.get_all()
    priority_map = {slug: i for i, slug in enumerate(REPORT_PRIORITIES)}
    for r in all_reports:
        r.category = REPORT_CATEGORIES.get(r.slug, 'general')
    sorted_reports = sorted(all_reports, key=lambda r: priority_map.get(r.slug, 999))
    return render(request, "reports/index.html", {
        "reports": sorted_reports,
        "units": Unit.objects.filter(is_active=True),
        "internal_sections": InternalSection.objects.filter(is_active=True),
    })


@login_required
def management_workbook(request):
    filters, filter_errors = _get_filters_from_request(request)
    if filter_errors:
        return HttpResponse("; ".join(filter_errors), status=400, content_type="text/plain")
    workbook_bytes = export_management_workbook(filters)
    response = HttpResponse(workbook_bytes, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="ABMS_Management_Report.xlsx"'
    return response


@login_required
def budget_word_document(request):
    """Generate and stream the formal Budget Analysis & Proposed Budget Word (.docx) document.
    Dynamically adheres to the user's active account and financial year.
    """
    from core.models import FutureBudget, FinancialYear
    from core.budget_word_report import generate_budget_word_report
    from core.future_budget_services import build_future_budget_lines

    account = request.account
    active_fy = request.fy

    if not account:
        return HttpResponse("No active account selected.", status=400, content_type="text/plain")

    # Determine target and source FY:
    # If active_fy is the target (e.g. 2026-27), look for budget targeting it.
    # If active_fy is 2025-26, look for budget with source_fy or target_fy matching active_fy.
    budget = None
    if active_fy:
        budget = FutureBudget.objects.filter(account=account, target_fy=active_fy).order_by('-created_at').first()
        if not budget:
            budget = FutureBudget.objects.filter(account=account, source_fy=active_fy).order_by('-created_at').first()

    # Fallback to latest for this account
    if not budget:
        budget = FutureBudget.objects.filter(account=account).order_by('-created_at').first()

    # If no budget exists for this account, dynamically auto-create one from the active and previous/next FY
    if not budget:
        all_fys = list(FinancialYear.objects.all().order_by('start_date'))
        if len(all_fys) >= 2:
            src_fy = all_fys[0]
            tgt_fy = all_fys[1]
        elif len(all_fys) == 1:
            src_fy = all_fys[0]
            tgt_fy = all_fys[0]
        else:
            return HttpResponse("No financial years configured.", status=404, content_type="text/plain")

        budget, created = FutureBudget.objects.get_or_create(
            account=account,
            source_fy=src_fy,
            target_fy=tgt_fy,
            defaults={
                'status': FutureBudget.Status.DRAFT,
                'reference': f'Auto-generated for {account.code}',
                'remarks': 'Auto-initialized for Word Report generation',
            }
        )
        if created:
            try:
                build_future_budget_lines(budget)
            except Exception:
                pass

    docx_bytes = generate_budget_word_report(budget)
    response = HttpResponse(
        docx_bytes,
        content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )
    safe_acct = budget.account.code.replace(' ', '_')
    safe_fy = budget.target_fy.code.replace(' ', '_')
    response['Content-Disposition'] = f'attachment; filename="Budget_Analysis_{safe_acct}_{safe_fy}.docx"'
    return response


def _build_unit_monthly_matrix(filters):
    acc = filters.get("account")
    fy = filters.get("financial_year")
    if not acc or not fy:
        return None
    qs = Transaction.objects.filter(account=acc, financial_year=fy, status="ACTIVE", direction="OUTFLOW", unit__isnull=False)
    if filters.get("start_date"):
        qs = qs.filter(transaction_date__gte=filters["start_date"])
    if filters.get("end_date"):
        qs = qs.filter(transaction_date__lte=filters["end_date"])
    if filters.get("unit_ids"):
        qs = qs.filter(unit_id__in=filters["unit_ids"])
    units = sorted(list(set(qs.values_list("unit__name", flat=True).distinct())))
    if not units:
        return None
    all_months = sorted(list(set(d.strftime("%Y-%m") for d in qs.values_list("transaction_date", flat=True))))
    matrix_rows = []
    col_totals = {u: Decimal("0.00") for u in units}
    grand_total = Decimal("0.00")
    for m in all_months:
        y, mo = int(m[:4]), int(m[5:7])
        m_qs = qs.filter(transaction_date__year=y, transaction_date__month=mo)
        m_sums = {r["unit__name"]: r["tot"] for r in m_qs.values("unit__name").annotate(tot=Sum("amount"))}
        row_cols = {}
        row_tot = Decimal("0.00")
        for u in units:
            val = m_sums.get(u, Decimal("0.00"))
            row_cols[u] = val
            row_tot += val
            col_totals[u] += val
        grand_total += row_tot
        matrix_rows.append({"month": m, "cols": row_cols, "total": row_tot})
    return {
        "title": "Monthly Unit Expenditure Breakdown",
        "columns": units,
        "rows": matrix_rows,
        "totals": {"cols": col_totals, "total": grand_total},
    }


def _build_section_monthly_matrix(filters):
    acc = filters.get("account")
    fy = filters.get("financial_year")
    if not acc or not fy:
        return None
    qs = Transaction.objects.filter(account=acc, financial_year=fy, status="ACTIVE", direction="OUTFLOW", internal_section__isnull=False)
    if filters.get("start_date"):
        qs = qs.filter(transaction_date__gte=filters["start_date"])
    if filters.get("end_date"):
        qs = qs.filter(transaction_date__lte=filters["end_date"])
    if filters.get("internal_section_ids"):
        qs = qs.filter(internal_section_id__in=filters["internal_section_ids"])
    sections = sorted(list(set(qs.values_list("internal_section__name", flat=True).distinct())))
    if not sections:
        return None
    all_months = sorted(list(set(d.strftime("%Y-%m") for d in qs.values_list("transaction_date", flat=True))))
    matrix_rows = []
    col_totals = {s: Decimal("0.00") for s in sections}
    grand_total = Decimal("0.00")
    for m in all_months:
        y, mo = int(m[:4]), int(m[5:7])
        m_qs = qs.filter(transaction_date__year=y, transaction_date__month=mo)
        m_sums = {r["internal_section__name"]: r["tot"] for r in m_qs.values("internal_section__name").annotate(tot=Sum("amount"))}
        row_cols = {}
        row_tot = Decimal("0.00")
        for s in sections:
            val = m_sums.get(s, Decimal("0.00"))
            row_cols[s] = val
            row_tot += val
            col_totals[s] += val
        grand_total += row_tot
        matrix_rows.append({"month": m, "cols": row_cols, "total": row_tot})
    return {
        "title": "Monthly Internal Section Expenditure Breakdown",
        "columns": sections,
        "rows": matrix_rows,
        "totals": {"cols": col_totals, "total": grand_total},
    }


def _build_head_monthly_matrix(filters):
    acc = filters.get("account")
    fy = filters.get("financial_year")
    if not acc or not fy:
        return None
    qs = Transaction.objects.filter(account=acc, financial_year=fy, status="ACTIVE", direction="OUTFLOW", account_head__isnull=False)
    if filters.get("start_date"):
        qs = qs.filter(transaction_date__gte=filters["start_date"])
    if filters.get("end_date"):
        qs = qs.filter(transaction_date__lte=filters["end_date"])
    if filters.get("account_head"):
        qs = qs.filter(account_head_id=filters["account_head"])
    heads_ordered = [h["account_head__name"] for h in qs.values("account_head__name").annotate(tot=Sum("amount")).order_by("-tot")]
    if not heads_ordered:
        return None
    top_heads = heads_ordered[:7]
    has_other = len(heads_ordered) > 7
    matrix_cols = list(top_heads)
    if has_other:
        matrix_cols.append("Other Heads")
    all_months = sorted(list(set(d.strftime("%Y-%m") for d in qs.values_list("transaction_date", flat=True))))
    matrix_rows = []
    col_totals = {h: Decimal("0.00") for h in matrix_cols}
    grand_total = Decimal("0.00")
    for m in all_months:
        y, mo = int(m[:4]), int(m[5:7])
        m_qs = qs.filter(transaction_date__year=y, transaction_date__month=mo)
        m_sums = {r["account_head__name"]: r["tot"] for r in m_qs.values("account_head__name").annotate(tot=Sum("amount"))}
        row_cols = {}
        row_tot = Decimal("0.00")
        for h in top_heads:
            val = m_sums.get(h, Decimal("0.00"))
            row_cols[h] = val
            row_tot += val
            col_totals[h] += val
        if has_other:
            other_val = sum(m_sums.get(h, Decimal("0.00")) for h in heads_ordered[7:])
            row_cols["Other Heads"] = other_val
            row_tot += other_val
            col_totals["Other Heads"] += other_val
        grand_total += row_tot
        matrix_rows.append({"month": m, "cols": row_cols, "total": row_tot})
    return {
        "title": "Monthly Account Head Expenditure Breakdown",
        "columns": matrix_cols,
        "rows": matrix_rows,
        "totals": {"cols": col_totals, "total": grand_total},
    }


@login_required
def view_report(request, slug):
    from core.services import (
        get_total_pass_through, get_pass_through_inflows,
        get_total_actual_inflows, get_total_actual_outflows,
        get_opening_balance, get_balance_available, get_period_summary
    )
    report_def = registry.get_report(slug)
    if not report_def:
        raise Http404("Report not found")
    filters, filter_errors = _get_filters_from_request(request)
    selected_fys = filters.get("selected_fys", [])
    fy_sections = []
    grand_totals = {}
    pass_through_total = Decimal("0.00")
    gross_total = Decimal("0.00")
    report_pass_through = Decimal("0.00")
    report_gross_total = Decimal("0.00")

    if filter_errors:
        dataset = []
        totals = {}
    elif len(selected_fys) > 1:
        for fy in selected_fys:
            fy_filter = {**filters, "financial_year": fy}
            fy_data = report_def.builder_func(fy_filter)
            fy_data = _trim_month_rows_to_selected_range(fy_data, fy_filter)
            fy_t = {}
            if report_def.totals and fy_data:
                for total_key in report_def.totals:
                    running = Decimal("0.00")
                    for row in fy_data:
                        val = row.get(total_key)
                        if val is not None:
                            try:
                                running += Decimal(str(val))
                            except Exception:
                                pass
                    fy_t[total_key] = running
            if slug == 'monthly-inflows' or filters.get('direction') == 'INFLOW':
                fy_pt = get_pass_through_inflows(filters.get("account"), fy, filters.get("start_date"), filters.get("end_date"))
            else:
                fy_pt = get_total_pass_through(filters.get("account"), fy, filters.get("start_date"), filters.get("end_date"))
            outflow_k = next((k for k in ("amount", "total_outflows", "outflows", "budget_consumed") if k in fy_t), None)
            if slug in ('account-summary', 'fy-summary') and fy_data:
                fy_gross = sum(Decimal(str(r.get('total_outflows') or 0)) for r in fy_data)
            elif slug == 'yoy-comparative':
                fy_gross = fy_t.get('curr_actual', Decimal('0.00')) + fy_pt
            elif slug == 'routine-vs-addl':
                fy_gross = fy_t.get('total', Decimal('0.00'))
            elif 'operational_outflows' in fy_t:
                fy_gross = fy_t.get('amount', fy_t.get('outflows', fy_t['operational_outflows'] + fy_pt))
            elif outflow_k == 'budget_consumed':
                fy_gross = fy_t[outflow_k] + fy_pt
            elif outflow_k:
                fy_gross = fy_t[outflow_k]
            else:
                fy_gross = fy_pt
            fy_sections.append({
                "fy": fy,
                "dataset": fy_data,
                "totals": fy_t,
                "pass_through": fy_pt,
                "gross_total": fy_gross,
            })
        for total_key in (report_def.totals or []):
            grand_totals[total_key] = sum(s["totals"].get(total_key, Decimal("0.00")) for s in fy_sections)
        pass_through_total = sum(s.get("pass_through", Decimal("0.00")) for s in fy_sections)
        gross_total = sum(s.get("gross_total", Decimal("0.00")) for s in fy_sections)
        dataset = []
        for s in fy_sections:
            dataset.extend(s["dataset"])
        totals = grand_totals
        report_pass_through = pass_through_total
        report_gross_total = gross_total
    else:
        dataset = report_def.builder_func(filters)
        dataset = _trim_month_rows_to_selected_range(dataset, filters)
        totals = {}
        if report_def.totals and dataset:
            for total_key in report_def.totals:
                running = Decimal("0.00")
                for row in dataset:
                    value = row.get(total_key)
                    if value is not None:
                        try:
                            running += Decimal(str(value))
                        except Exception:
                            pass
                totals[total_key] = running
        active_fy = selected_fys[0] if selected_fys else filters.get("financial_year")
        if slug == 'monthly-inflows' or filters.get('direction') == 'INFLOW':
            report_pass_through = get_pass_through_inflows(filters.get("account"), active_fy, filters.get("start_date"), filters.get("end_date"))
        else:
            report_pass_through = get_total_pass_through(filters.get("account"), active_fy, filters.get("start_date"), filters.get("end_date"))
        outflow_k = next((k for k in ("amount", "total_outflows", "outflows", "budget_consumed") if k in totals), None)
        if slug in ('account-summary', 'fy-summary') and dataset:
            report_gross_total = sum(Decimal(str(r.get('total_outflows') or 0)) for r in dataset)
        elif slug == 'yoy-comparative':
            report_gross_total = totals.get('curr_actual', Decimal('0.00')) + report_pass_through
        elif slug == 'routine-vs-addl':
            report_gross_total = totals.get('total', Decimal('0.00'))
        elif 'operational_outflows' in totals:
            report_gross_total = totals.get('amount', totals.get('outflows', totals['operational_outflows'] + report_pass_through))
        elif outflow_k == 'budget_consumed':
            report_gross_total = (totals[outflow_k] + report_pass_through)
        elif outflow_k:
            report_gross_total = totals[outflow_k]
        else:
            report_gross_total = report_pass_through
        pass_through_total = report_pass_through
        gross_total = report_gross_total
        if selected_fys:
            fy_sections = [{"fy": selected_fys[0], "dataset": dataset, "totals": totals, "pass_through": report_pass_through, "gross_total": report_gross_total}]

    # Matrix breakdown for reports requiring cross-tabulation by Month (Units, Sections, Account Heads)
    matrix_breakdown = None
    if not filter_errors:
        if slug == "unit-summary":
            matrix_breakdown = _build_unit_monthly_matrix(filters)
        elif slug == "internal-section-summary":
            matrix_breakdown = _build_section_monthly_matrix(filters)
        elif slug == "account-head-summary":
            matrix_breakdown = _build_head_monthly_matrix(filters)

    # Detailed Cash Flow Monthly Breakdown (strictly for financial/executive overview reports)
    monthly_breakdown = []
    monthly_totals = {}
    SLUGS_WITH_MONTHLY_CASH_FLOW = {
        "account-summary",
        "fy-summary",
        "pass-through-summary",
        "budget-vs-actual",
        "yoy-comparative",
        "budget-utilisation",
    }
    if not filter_errors and slug in SLUGS_WITH_MONTHLY_CASH_FLOW:
        acc = filters.get("account")
        target_fys = selected_fys if selected_fys else ([filters.get("financial_year")] if filters.get("financial_year") else [])
        if acc and target_fys:
            from core.services import get_opening_balance
            from core.models import Transaction

            tot_op_inflows = Decimal("0.00")
            tot_pt_inflows = Decimal("0.00")
            tot_inflows = Decimal("0.00")
            tot_outflows = Decimal("0.00")
            tot_op_outflows = Decimal("0.00")
            tot_pt_outflows = Decimal("0.00")
            tot_net = Decimal("0.00")
            running_balance = Decimal("0.00")
            is_first_fy = True

            for fy_idx, fy in enumerate(target_fys):
                trend_filters = {
                    "account": acc,
                    "financial_year": fy,
                }
                if filters.get("start_date"):
                    trend_filters["start_date"] = filters.get("start_date")
                if filters.get("end_date"):
                    trend_filters["end_date"] = filters.get("end_date")
                trend = services.build_monthly_trend(trend_filters)
                trend = _trim_month_rows_to_selected_range(trend, trend_filters)

                if is_first_fy:
                    start_date = trend_filters.get("start_date")
                    if start_date:
                        prior_inflows = Transaction.objects.filter(
                            account=acc,
                            financial_year=fy,
                            direction=Transaction.Direction.INFLOW,
                            status=Transaction.Status.ACTIVE,
                            transaction_date__lt=start_date,
                        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
                        prior_outflows = Transaction.objects.filter(
                            account=acc,
                            financial_year=fy,
                            direction=Transaction.Direction.OUTFLOW,
                            status=Transaction.Status.ACTIVE,
                            transaction_date__lt=start_date,
                        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
                        running_balance = get_opening_balance(acc, fy) + prior_inflows - prior_outflows
                    else:
                        running_balance = get_opening_balance(acc, fy)
                    is_first_fy = False
                else:
                    fy_ob = get_opening_balance(acc, fy)
                    if fy_ob > Decimal("0.00"):
                        running_balance = fy_ob

                for row in trend:
                    m_ob = running_balance
                    m_in = row.get("inflows", Decimal("0.00"))
                    m_out = row.get("outflows", Decimal("0.00"))
                    m_op = row.get("operational_outflows", m_out)
                    m_pt = row.get("pass_through", Decimal("0.00"))
                    m_str = row.get("month", "2000-01")
                    try:
                        y, mo = int(m_str[:4]), int(m_str[5:7])
                        m_pt_in = Transaction.objects.filter(
                            account=acc, financial_year=fy,
                            direction=Transaction.Direction.INFLOW,
                            status=Transaction.Status.ACTIVE,
                            pass_through=True,
                            transaction_date__year=y, transaction_date__month=mo,
                        ).aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
                    except Exception:
                        m_pt_in = Decimal("0.00")
                    m_op_in = max(Decimal("0.00"), m_in - m_pt_in)
                    m_net = m_in - m_out
                    running_balance = m_ob + m_net
                    tot_op_inflows += m_op_in
                    tot_pt_inflows += m_pt_in
                    tot_inflows += m_in
                    tot_outflows += m_out
                    tot_op_outflows += m_op
                    tot_pt_outflows += m_pt
                    tot_net += m_net
                    monthly_breakdown.append({
                        "month": m_str,
                        "fy_name": fy.name,
                        "opening_balance": m_ob,
                        "operational_inflows": m_op_in,
                        "pass_through_inflows": m_pt_in,
                        "inflows": m_in,
                        "operational_outflows": m_op,
                        "pass_through": m_pt,
                        "outflows": m_out,
                        "net_movement": m_net,
                        "closing_balance": running_balance,
                    })

            monthly_totals = {
                "operational_inflows": tot_op_inflows,
                "pass_through_inflows": tot_pt_inflows,
                "inflows": tot_inflows,
                "operational_outflows": tot_op_outflows,
                "pass_through": tot_pt_outflows,
                "outflows": tot_outflows,
                "net_movement": tot_net,
            }

    has_date_range = bool(filters.get("start_date") or filters.get("end_date"))
    if filters.get("start_date") and filters.get("end_date"):
        date_scope_label = f"{filters['start_date']:%d-%m-%Y} to {filters['end_date']:%d-%m-%Y}"
    elif filters.get("start_date"):
        date_scope_label = f"From {filters['start_date']:%d-%m-%Y}"
    elif filters.get("end_date"):
        date_scope_label = f"Up to {filters['end_date']:%d-%m-%Y}"
    elif len(selected_fys) > 1:
        date_scope_label = f"{len(selected_fys)} Financial Years: " + ", ".join(f.code for f in selected_fys)
    else:
        date_scope_label = f"Full Financial Year ({selected_fys[0].name if selected_fys else 'Active'})"

    acc = filters.get("account")
    major_heads = MajorHead.objects.filter(account=acc).order_by('display_order', 'name') if acc else MajorHead.objects.none()
    account_heads = AccountHead.objects.filter(account=acc).order_by('name') if acc else AccountHead.objects.none()
    sub_heads = SubHead.objects.filter(account=acc).order_by('name') if acc else SubHead.objects.none()

    applied_filters = []
    if acc:
        applied_filters.append({'label': 'Acct / Fund', 'value': acc.name})
    if selected_fys:
        applied_filters.append({'label': 'Fin Yr', 'value': ', '.join(f.code for f in selected_fys)})
    if has_date_range:
        applied_filters.append({'label': 'Date Range', 'value': date_scope_label})
    if filters.get('direction'):
        dir_label = {'INFLOW': 'Inflow Only', 'OUTFLOW': 'Outflow Only'}.get(filters['direction'], filters['direction'])
        applied_filters.append({'label': 'Txn Type (Dir)', 'value': dir_label})
    if filters.get('major_head'):
        try:
            mh_obj = major_heads.filter(pk=int(filters['major_head'])).first()
            mh_name = mh_obj.name if mh_obj else str(filters['major_head'])
        except (ValueError, TypeError):
            mh_name = str(filters['major_head'])
        applied_filters.append({'label': 'Sub Fund (Tier 1)', 'value': mh_name})
    if filters.get('account_head'):
        try:
            ah_obj = account_heads.filter(pk=int(filters['account_head'])).first()
            ah_name = ah_obj.name if ah_obj else str(filters['account_head'])
        except (ValueError, TypeError):
            ah_name = str(filters['account_head'])
        applied_filters.append({'label': 'Acct Head (Tier 2)', 'value': ah_name})
    if filters.get('sub_head'):
        try:
            sh_obj = sub_heads.filter(pk=int(filters['sub_head'])).first()
            sh_name = sh_obj.name if sh_obj else str(filters['sub_head'])
        except (ValueError, TypeError):
            sh_name = str(filters['sub_head'])
        applied_filters.append({'label': 'Sub Head (Tier 3)', 'value': sh_name})
    if filters.get('search'):
        applied_filters.append({'label': 'Search Keyword', 'value': filters['search']})
    if filters.get('unit'):
        u_obj = Unit.objects.filter(pk=filters['unit']).first() if str(filters['unit']).isdigit() else None
        if u_obj:
            applied_filters.append({'label': 'Unit', 'value': u_obj.name})
    if filters.get('internal_section'):
        sec_obj = InternalSection.objects.filter(pk=filters['internal_section']).first() if str(filters['internal_section']).isdigit() else None
        if sec_obj:
            applied_filters.append({'label': 'Internal Sec', 'value': sec_obj.name})
    if filters.get('cohort'):
        c_obj = Cohort.objects.filter(pk=filters['cohort']).first() if str(filters['cohort']).isdigit() else None
        if c_obj:
            applied_filters.append({'label': 'Cohort', 'value': c_obj.name})
    if filters.get('package'):
        pkg_obj = CohortPackage.objects.filter(pk=filters['package']).first() if str(filters['package']).isdigit() else None
        if pkg_obj:
            applied_filters.append({'label': 'Cohort Package', 'value': f"{pkg_obj.package_name} ({pkg_obj.package_code})"})
    if filters.get('tour_operator'):
        to_obj = TourOperator.objects.filter(pk=filters['tour_operator']).first() if str(filters['tour_operator']).isdigit() else None
        if to_obj:
            applied_filters.append({'label': 'Tour Operator', 'value': to_obj.name})
    if filters.get('pilgrim'):
        p_obj = Pilgrim.objects.filter(pk=filters['pilgrim']).first() if str(filters['pilgrim']).isdigit() else None
        if p_obj:
            applied_filters.append({'label': 'Pilgrim', 'value': str(p_obj)})
    if filters.get('ceremony_event'):
        pe_obj = CeremonyEvent.objects.filter(pk=filters['ceremony_event']).first() if str(filters['ceremony_event']).isdigit() else None
        if pe_obj:
            applied_filters.append({'label': 'Event', 'value': pe_obj.name})
    if filters.get('ceremony_venue'):
        pv_obj = CeremonyVenue.objects.filter(pk=filters['ceremony_venue']).first() if str(filters['ceremony_venue']).isdigit() else None
        if pv_obj:
            applied_filters.append({'label': 'Venue', 'value': pv_obj.name})

    dt_normal_inflows = Decimal("0.00")
    dt_normal_outflows = Decimal("0.00")
    dt_pt_inflows = Decimal("0.00")
    dt_pt_outflows = Decimal("0.00")
    dt_inflows_total = Decimal("0.00")
    dt_outflows_total = Decimal("0.00")

    fy = filters.get("financial_year") or (selected_fys[0] if selected_fys else None)

    if slug == 'dynamic-transactions' and dataset:
        for r in dataset:
            amt = Decimal(str(r.get('amount') or 0))
            is_pt = bool(r.get('pass_through'))
            d = r.get('direction')
            if d == 'INFLOW':
                if is_pt:
                    dt_pt_inflows += amt
                else:
                    dt_normal_inflows += amt
            elif d == 'OUTFLOW':
                if is_pt:
                    dt_pt_outflows += amt
                else:
                    dt_normal_outflows += amt
        dt_inflows_total = dt_normal_inflows + dt_pt_inflows
        dt_outflows_total = dt_normal_outflows + dt_pt_outflows
    elif slug in ('account-summary', 'fy-summary', 'monthly-trend', 'yoy-comparative', 'pass-through-summary', 'budget-vs-actual', 'budget-utilisation') and acc and (fy or selected_fys):
        from core.services import (
            get_total_actual_inflows, get_pass_through_inflows,
            get_total_actual_outflows, get_total_pass_through
        )
        target_fys = selected_fys if selected_fys else ([fy] if fy else [])
        for f in target_fys:
            s_date = filters.get('start_date')
            e_date = filters.get('end_date')
            f_in = get_total_actual_inflows(acc, f, s_date, e_date)
            f_pt_in = get_pass_through_inflows(acc, f, s_date, e_date)
            f_out = get_total_actual_outflows(acc, f, s_date, e_date)
            f_pt_out = get_total_pass_through(acc, f, s_date, e_date)

            dt_inflows_total += f_in
            dt_pt_inflows += f_pt_in
            dt_normal_inflows += max(Decimal('0.00'), f_in - f_pt_in)

            dt_outflows_total += f_out
            dt_pt_outflows += f_pt_out
            dt_normal_outflows += max(Decimal('0.00'), f_out - f_pt_out)

    dt_net_movement = dt_inflows_total - dt_outflows_total
    dt_tx_count = len(dataset)

    # 1. Opening and Closing Balances
    opening_balance = Decimal("0.00")
    closing_balance = Decimal("0.00")

    if slug in ('account-summary', 'fy-summary') and dataset:
        opening_balance = sum(Decimal(str(r.get('opening_balance') or 0)) for r in dataset)
        closing_balance = sum(Decimal(str(r.get('balance_available') or 0)) for r in dataset)
    elif slug == 'dynamic-transactions':
        if acc and fy:
            from core.services import get_opening_balance
            start_date = filters.get("start_date")
            if start_date:
                from core.models import Transaction
                prior_inflows = Transaction.objects.filter(
                    account=acc,
                    financial_year=fy,
                    direction=Transaction.Direction.INFLOW,
                    status=Transaction.Status.ACTIVE,
                    transaction_date__lt=start_date,
                ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
                prior_outflows = Transaction.objects.filter(
                    account=acc,
                    financial_year=fy,
                    direction=Transaction.Direction.OUTFLOW,
                    status=Transaction.Status.ACTIVE,
                    transaction_date__lt=start_date,
                ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
                opening_balance = get_opening_balance(acc, fy) + prior_inflows - prior_outflows
            else:
                opening_balance = get_opening_balance(acc, fy)
        closing_balance = opening_balance + dt_net_movement
    elif acc and fy:
        from core.services import get_opening_balance, get_balance_available, get_period_summary
        start_date = filters.get("start_date")
        end_date = filters.get("end_date")
        if start_date or end_date:
            period_data = get_period_summary(acc, fy, start_date or fy.start_date, end_date)
            opening_balance = period_data['period_opening_balance']
            closing_balance = period_data['period_closing_balance']
        elif len(selected_fys) > 1:
            opening_balance = get_opening_balance(acc, selected_fys[0])
            closing_balance = get_balance_available(acc, selected_fys[-1])
        else:
            opening_balance = get_opening_balance(acc, fy)
            closing_balance = get_balance_available(acc, fy)

    # 2. Excl. Pass-Through & Gross Totals
    if slug in ('account-summary', 'fy-summary') and dataset:
        excl_pt_total = sum(Decimal(str(r.get('budget_consumed') or 0)) for r in dataset)
        report_gross_total = sum(Decimal(str(r.get('total_outflows') or 0)) for r in dataset)
        if not excl_pt_total and report_gross_total:
            excl_pt_total = max(Decimal("0.00"), report_gross_total - report_pass_through)
    elif slug == 'yoy-comparative':
        excl_pt_total = totals.get('curr_actual', Decimal('0.00'))
        report_gross_total = excl_pt_total + report_pass_through
    elif 'operational_inflows' in totals and (slug == 'monthly-inflows' or filters.get('direction') == 'INFLOW'):
        excl_pt_total = totals['operational_inflows']
        report_gross_total = totals.get('amount', totals.get('inflows', excl_pt_total + report_pass_through))
    elif 'operational_outflows' in totals:
        excl_pt_total = totals['operational_outflows']
        report_gross_total = totals.get('amount', totals.get('outflows', excl_pt_total + report_pass_through))
    elif slug == 'pass-through-summary' and dataset:
        excl_pt_total = sum(Decimal(str(r.get('other_outflows') or 0)) for r in dataset)
        report_gross_total = sum(Decimal(str(r.get('total_outflows') or 0)) for r in dataset)
    elif slug == 'routine-vs-addl':
        excl_pt_total = totals.get('routine', Decimal('0.00')) + totals.get('addl', Decimal('0.00'))
        report_gross_total = totals.get('total', Decimal('0.00'))
    elif 'budget_consumed' in totals:
        excl_pt_total = totals['budget_consumed']
        report_gross_total = excl_pt_total + report_pass_through
    elif 'amount' in totals:
        if filters.get('direction') == 'INFLOW' or slug == 'monthly-inflows':
            pt_in = get_pass_through_inflows(acc, fy) if acc and fy else Decimal('0.00')
            report_gross_total = totals['amount']
            excl_pt_total = max(Decimal("0.00"), report_gross_total - pt_in)
        elif slug in ('unit-summary', 'internal-section-summary', 'unit-section-summary', 'organisational-transactions'):
            report_gross_total = totals['amount']
            excl_pt_total = totals['amount']
        else:
            if filters.get('pass_through') is True:
                report_gross_total = totals['amount']
                excl_pt_total = Decimal('0.00')
            elif filters.get('pass_through') is False:
                excl_pt_total = totals['amount']
                report_gross_total = excl_pt_total
            else:
                report_gross_total = totals['amount']
                excl_pt_total = max(Decimal("0.00"), report_gross_total - report_pass_through)
    elif 'outflows' in totals:
        report_gross_total = totals['outflows']
        excl_pt_total = max(Decimal("0.00"), report_gross_total - report_pass_through)
    else:
        excl_pt_total = Decimal("0.00")
        if totals:
            for k in ("amount", "total_outflows", "outflows", "budget_consumed", "total_inflows"):
                if k in totals:
                    excl_pt_total = totals[k]
                    break
        if not excl_pt_total and dataset:
            for k in ("budget_consumed", "amount", "total_outflows", "total"):
                if any(k in r for r in dataset):
                    excl_pt_total = sum(Decimal(str(r.get(k) or 0)) for r in dataset)
                    break
        if not report_gross_total:
            report_gross_total = excl_pt_total + report_pass_through

    gross_total = report_gross_total
    pass_through_total = report_pass_through
    if fy_sections and len(selected_fys) <= 1:
        fy_sections[0]["gross_total"] = report_gross_total

    # Derive the authoritative primary total for this report
    report_primary_total = Decimal("0.00")
    if totals:
        for k in ("amount", "total_outflows", "outflows", "budget_consumed", "total", "operational_outflows", "curr_actual", "total_inflows"):
            if k in totals and totals[k] is not None:
                report_primary_total = totals[k]
                break
    if not report_primary_total and dataset:
        for k in ("amount", "total_outflows", "outflows", "budget_consumed", "total"):
            if any(k in r for r in dataset):
                report_primary_total = sum(Decimal(str(r.get(k) or 0)) for r in dataset)
                break

    report_kpis = {
        'total_records': len(dataset),
        'report_total': report_primary_total,
        'report_total_mn': (report_primary_total / Decimal('1000000')).quantize(Decimal('0.01')),
        'is_dynamic_tx': slug == 'dynamic-transactions',
        'is_financial_summary': slug in ('dynamic-transactions', 'fy-summary', 'account-summary', 'pass-through-summary', 'monthly-trend', 'yoy-comparative', 'budget-vs-actual', 'budget-utilisation', 'present-sub-fund-balance', 'present-account-head-balance', 'present-sub-account-head-balance'),
        'opening_balance': opening_balance,
        'closing_balance': closing_balance,
        'opening_balance_mn': (opening_balance / Decimal('1000000')).quantize(Decimal('0.01')),
        'closing_balance_mn': (closing_balance / Decimal('1000000')).quantize(Decimal('0.01')),
        # Inflows (Excl, PT, Incl)
        'dt_normal_inflows': dt_normal_inflows,
        'dt_normal_inflows_mn': (dt_normal_inflows / Decimal('1000000')).quantize(Decimal('0.01')),
        'dt_pt_inflows': dt_pt_inflows,
        'dt_pt_inflows_mn': (dt_pt_inflows / Decimal('1000000')).quantize(Decimal('0.01')),
        'dt_total_inflows': dt_inflows_total,
        'dt_total_inflows_mn': (dt_inflows_total / Decimal('1000000')).quantize(Decimal('0.01')),
        # Outflows (Excl, PT, Incl)
        'dt_normal_outflows': dt_normal_outflows,
        'dt_normal_outflows_mn': (dt_normal_outflows / Decimal('1000000')).quantize(Decimal('0.01')),
        'dt_pt_outflows': dt_pt_outflows,
        'dt_pt_outflows_mn': (dt_pt_outflows / Decimal('1000000')).quantize(Decimal('0.01')),
        'dt_total_outflows': dt_outflows_total,
        'dt_total_outflows_mn': (dt_outflows_total / Decimal('1000000')).quantize(Decimal('0.01')),
        # Net Movement & Pass-Through Transfers
        'dt_normal_net': dt_normal_inflows - dt_normal_outflows,
        'dt_normal_net_mn': ((dt_normal_inflows - dt_normal_outflows) / Decimal('1000000')).quantize(Decimal('0.01')),
        'dt_pt_transfers': dt_pt_inflows + dt_pt_outflows,
        'dt_pt_transfers_mn': ((dt_pt_inflows + dt_pt_outflows) / Decimal('1000000')).quantize(Decimal('0.01')),
        'dt_net_movement': dt_net_movement,
        'dt_net_movement_mn': (dt_net_movement / Decimal('1000000')).quantize(Decimal('0.01')),
        # Standard reports
        'excl_pt_total': excl_pt_total,
        'excl_pt_total_mn': (excl_pt_total / Decimal('1000000')).quantize(Decimal('0.01')),
        'pt_total': report_pass_through,
        'pt_total_mn': (report_pass_through / Decimal('1000000')).quantize(Decimal('0.01')),
        'incl_pt_total': report_gross_total if report_gross_total else (excl_pt_total + report_pass_through),
        'incl_pt_total_mn': ((report_gross_total if report_gross_total else (excl_pt_total + report_pass_through)) / Decimal('1000000')).quantize(Decimal('0.01')),
        'fund_code': acc.code if acc else 'NGL',
    }

    REPORTS_WITH_PT_FOOTER = set()
    show_pt_reconciliation_footer = bool(
        slug in REPORTS_WITH_PT_FOOTER
        and report_pass_through > Decimal('0.00')
    )

    # Fund-specific model querysets
    cohorts = Cohort.objects.all().order_by('-code')
    packages = CohortPackage.objects.filter(is_active=True).select_related('cohort').order_by('cohort__code', 'package_name')
    tour_operators = TourOperator.objects.filter(is_active=True).order_by('name')
    pilgrims = Pilgrim.objects.all()[:100]
    ceremony_events = CeremonyEvent.objects.all().order_by('-event_year', 'name')
    ceremony_venues = CeremonyVenue.objects.filter(is_active=True).order_by('name')

    context = {
        "report": report_def,
        "show_pt_reconciliation_footer": show_pt_reconciliation_footer,
        "matrix_breakdown": matrix_breakdown,
        "dataset": dataset,
        "totals": totals,
        "fy_sections": fy_sections,
        "grand_totals": grand_totals,
        "is_multi_fy": len(selected_fys) > 1,
        "available_fys": FinancialYear.objects.all().order_by('start_date'),
        "selected_fy_ids": [f.pk for f in selected_fys],
        "filters": filters,
        "filter_errors": filter_errors,
        "has_date_range": has_date_range,
        "date_scope_label": date_scope_label,
        "report_date_basis": "Transaction Date entered on the financial record for transaction-based reports",
        "units": Unit.objects.filter(is_active=True),
        "internal_sections": InternalSection.objects.filter(is_active=True),
        "selected_unit_ids": filters.get("unit_ids", []),
        "selected_internal_section_ids": filters.get("internal_section_ids", []),
        "monthly_breakdown": monthly_breakdown,
        "monthly_totals": monthly_totals,
        "pass_through_total": pass_through_total,
        "gross_total": gross_total,
        "report_pass_through": report_pass_through,
        "report_gross_total": report_gross_total,
        "applied_filters": applied_filters,
        "major_heads": major_heads,
        "account_heads": account_heads,
        "sub_heads": sub_heads,
        "selected_major_head": str(filters.get("major_head", "")),
        "selected_account_head": str(filters.get("account_head", "")),
        "selected_sub_head": str(filters.get("sub_head", "")),
        "selected_direction": str(filters.get("direction", "")),
        "selected_unit": str(filters.get("unit", "")),
        "selected_internal_section": str(filters.get("internal_section", "")),
        "selected_cohort": str(filters.get("cohort", "")),
        "selected_package": str(filters.get("package", "")),
        "selected_tour_operator": str(filters.get("tour_operator", "")),
        "selected_pilgrim": str(filters.get("pilgrim", "")),
        "selected_ceremony_event": str(filters.get("ceremony_event", "")),
        "selected_ceremony_venue": str(filters.get("ceremony_venue", "")),
        "cohorts": cohorts,
        "packages": packages,
        "tour_operators": tour_operators,
        "pilgrims": pilgrims,
        "ceremony_events": ceremony_events,
        "ceremony_venues": ceremony_venues,
        "fund_code": acc.code if acc else 'NGL',
        "dt_inflows_total": dt_inflows_total,
        "dt_outflows_total": dt_outflows_total,
        "dt_net_movement": dt_net_movement,
        "dt_tx_count": dt_tx_count,
        "opening_balance": opening_balance,
        "closing_balance": closing_balance,
        "report_kpis": report_kpis,
    }

    fmt = request.GET.get("format")
    if not filter_errors and fmt == "management_excel":
        excel_bytes = export_management_workbook(filters)
        response = HttpResponse(excel_bytes, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = 'attachment; filename="ABMS_Management_Report.xlsx"'
        return response
    if not filter_errors and fmt == "pdf":
        pdf_bytes = export_to_pdf(
            report_def, dataset, filters,
            applied_filters=applied_filters,
            report_kpis=report_kpis,
            monthly_breakdown=monthly_breakdown,
            monthly_totals=monthly_totals,
            fy_sections=fy_sections,
            is_multi_fy=len(selected_fys) > 1,
            grand_totals=grand_totals,
        )
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{report_def.slug}.pdf"'
        return response
    if not filter_errors and fmt == "excel":
        excel_bytes = export_to_excel(
            report_def, dataset, filters,
            applied_filters=applied_filters,
            report_kpis=report_kpis,
            monthly_breakdown=monthly_breakdown,
            monthly_totals=monthly_totals,
            fy_sections=fy_sections,
            is_multi_fy=len(selected_fys) > 1,
            grand_totals=grand_totals,
        )
        response = HttpResponse(excel_bytes, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f'attachment; filename="{report_def.slug}.xlsx"'
        return response
    return render(request, "reports/report_view.html", context)
