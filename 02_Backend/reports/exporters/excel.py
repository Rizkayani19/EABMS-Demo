import io
from datetime import datetime
from decimal import Decimal

from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side


def _pakistan_now_label():
    local_now = timezone.localtime(
        timezone.now(),
        timezone.get_fixed_timezone(5 * 60)
    )
    return local_now.strftime('%d-%m-%Y %H:%M') + ' PKT (UTC+05:00)'


def _filter_label(filters, key, model_attr='name'):
    ids = filters.get(key, []) or []
    if not ids:
        return 'All'
    model = None
    if key == 'unit_ids':
        from core.models import Unit
        model = Unit
    elif key == 'internal_section_ids':
        from masters.models import InternalSection
        model = InternalSection
    if not model:
        return 'All'
    return ', '.join(
        model.objects.filter(pk__in=ids).values_list(model_attr, flat=True)
    ) or 'All'


def export_to_excel(report_def, dataset, filters, applied_filters=None, report_kpis=None, monthly_breakdown=None, monthly_totals=None, fy_sections=None, is_multi_fy=False, grand_totals=None):
    wb = Workbook()
    ws = wb.active

    sheet_title = report_def.title
    for char in ['\\', '/', '*', '?', ':', '[', ']']:
        sheet_title = sheet_title.replace(char, '-')
    ws.title = sheet_title[:31]

    # Page setup for printing
    ws.page_setup.orientation = ws.ORIENTATION_LANDSCAPE
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    # Corporate running header: Page X of Y & CONFIDENTIAL
    ws.oddHeader.center.text = "&P of &N\nCONFIDENTIAL"
    ws.oddHeader.center.size = 8
    ws.oddHeader.center.color = "BE123C"
    ws.oddFooter.center.text = "CONFIDENTIAL"
    ws.oddFooter.center.size = 8
    ws.oddFooter.center.color = "BE123C"

    # ---------------------------------------------------------
    # CORPORATE RUNNING HEADER (Centered on Top)
    # ---------------------------------------------------------
    ws.append(["CONFIDENTIAL"])
    ws.cell(row=1, column=1).font = Font(name='Segoe UI', size=9, bold=True, color='BE123C')
    ws.cell(row=1, column=1).alignment = Alignment(horizontal='center')

    # ---------------------------------------------------------
    # REPORT HEADER BLOCK (Center Aligned)
    # ---------------------------------------------------------
    ws.append(["EABMS — Enterprise Accounts & Business Management System"])
    title = getattr(report_def, 'title', 'Report')
    ws.append([f"Report: {title}"])

    acct_name = filters['account'].name if filters.get('account') else 'All Accts / Funds'
    fy_name = filters['financial_year'].name if filters.get('financial_year') else 'Active Fin Yr'
    selected_fys = filters.get('selected_fys', [])
    if is_multi_fy and selected_fys:
        fy_name = ", ".join(f.name for f in selected_fys)
    timestamp_str = _pakistan_now_label()

    ws.append([f"Acct / Fund: {acct_name} | Fin Yr: {fy_name} | Generated: {timestamp_str}"])

    if getattr(report_def, 'display_in_millions', False):
        ws.append(["(Amounts standardized in PKR Millions [Mn] unless otherwise indicated)"])
    else:
        ws.append(["(Amounts standardized in exact PKR [Rs] unless otherwise indicated)"])

    desc = getattr(report_def, 'description', '')
    if desc:
        ws.append([f"About This Report: {desc}"])

    ws.append([])

    # Applied Filters Block
    ws.append(["--- APPLIED FILTERS ---"])
    if applied_filters:
        for f_item in applied_filters:
            ws.append([f"{f_item['label']}: {f_item['value']}"])
    else:
        if filters.get('account'):
            ws.append([f"Acct: {filters['account'].name}"])
        if filters.get('financial_year'):
            ws.append([f"Fin Yr: {filters['financial_year'].name}"])
        start_date = filters.get('start_date')
        end_date = filters.get('end_date')
        if start_date or end_date:
            s_str = start_date.strftime('%d-%m-%Y') if hasattr(start_date, 'strftime') else str(start_date or 'Start')
            e_str = end_date.strftime('%d-%m-%Y') if hasattr(end_date, 'strftime') else str(end_date or 'End')
            ws.append([f"Period: {s_str} to {e_str}"])
        else:
            ws.append(["Period: Full active Fin Yr"])

        if 'unit_ids' in filters:
            ws.append([f"Unit(s): {_filter_label(filters, 'unit_ids')}"])
        if 'internal_section_ids' in filters:
            ws.append([f"Internal Sec(s): {_filter_label(filters, 'internal_section_ids')}"])

    ws.append([])

    # ---------------------------------------------------------
    # TOP KPI SUMMARY STRIP (PKR Millions [Mn])
    # ---------------------------------------------------------
    kpis = report_kpis or {}
    slug = getattr(report_def, 'slug', '')
    fund_code = kpis.get('fund_code', 'NGL')

    if slug in ('dynamic-transactions', 'fy-summary', 'account-summary', 'pass-through-summary', 'monthly-trend', 'yoy-comparative', 'budget-vs-actual', 'budget-utilisation') or kpis.get('is_financial_summary'):
        kpi_row1 = [
            "TOTAL TXNS & BALANCES",
            "TOTAL INFLOWS excl Pass-Through (PKR Mn)",
            "TOTAL OUTFLOWS excl Pass-Through (PKR Mn)",
            "NET MOVEMENT excl Pass-Through (PKR Mn)"
        ]
        kpi_row2 = [
            f"Records: {kpis.get('total_records', 0)} | Open: Rs {kpis.get('opening_balance_mn', 0)} Mn | Close: Rs {kpis.get('closing_balance_mn', 0)} Mn",
            f"Excl PT: Rs {kpis.get('dt_normal_inflows_mn', 0)} Mn | PT: Rs {kpis.get('dt_pt_inflows_mn', 0)} Mn | Grand Total incl PT: Rs {kpis.get('dt_total_inflows_mn', 0)} Mn",
            f"Excl PT: Rs {kpis.get('dt_normal_outflows_mn', 0)} Mn | PT: Rs {kpis.get('dt_pt_outflows_mn', 0)} Mn | Grand Total incl PT: Rs {kpis.get('dt_total_outflows_mn', 0)} Mn",
            f"Excl PT Net: Rs {kpis.get('dt_normal_net_mn', 0)} Mn | PT Tfrs: Rs {kpis.get('dt_pt_transfers_mn', 0)} Mn | Grand Total Net incl PT: Rs {kpis.get('dt_net_movement_mn', 0)} Mn"
        ]
        ws.append(kpi_row1)
        ws.append(kpi_row2)
    elif kpis:
        total_exp = kpis.get('report_total_mn')
        if total_exp is None or total_exp == Decimal('0.00'):
            total_exp = kpis.get('excl_pt_total_mn', Decimal('0.00'))
        kpi_row1 = [
            "TOTAL RECORDS",
            "TOTAL EXPENDITURE / AMOUNT (PKR Mn)",
            "FUND OPENING BALANCE (PKR Mn)",
            "FUND CLOSING BALANCE (PKR Mn)"
        ]
        kpi_row2 = [
            f"{kpis.get('total_records', 0)} records (Active Scope)",
            f"Rs {total_exp} Mn (Aggregated Scope Total)",
            f"Rs {kpis.get('opening_balance_mn', 0)} Mn (Starting Position)",
            f"Rs {kpis.get('closing_balance_mn', 0)} Mn (Available Cash Position)"
        ]
        ws.append(kpi_row1)
        ws.append(kpi_row2)

    ws.append([])

    # ---------------------------------------------------------
    # STYLING HEADER BLOCK
    # ---------------------------------------------------------
    title_font = Font(name='Segoe UI', size=14, bold=True, color='0F172A')
    subtitle_font = Font(name='Segoe UI', size=11, bold=True, color='047857')
    meta_font = Font(name='Segoe UI', size=9, bold=False, color='334155')
    italic_font = Font(name='Segoe UI', size=8.5, italic=True, color='64748B')
    about_font = Font(name='Segoe UI', size=9, italic=False, color='1E293B')

    ws.cell(row=2, column=1).font = title_font
    ws.cell(row=3, column=1).font = subtitle_font
    ws.cell(row=4, column=1).font = meta_font
    ws.cell(row=5, column=1).font = italic_font
    if report_def.description:
        ws.cell(row=6, column=1).font = about_font

    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )
    th_font = Font(name='Segoe UI', size=9.5, bold=True, color='0F172A')
    th_fill = PatternFill(start_color='E2E8F0', end_color='E2E8F0', fill_type='solid')

    def _append_generic_table(rows_data, totals_dict=None, pt_val=Decimal('0.00')):
        header_row = [col['label'] for col in report_def.columns]
        ws.append(header_row)
        h_idx = ws.max_row
        for c in range(1, len(header_row) + 1):
            cell = ws.cell(row=h_idx, column=c)
            cell.font = th_font
            cell.fill = th_fill
            cell.border = thin_border
            cell.alignment = Alignment(horizontal='center' if c in (1, 2) else 'left', vertical='center')

        running_totals = {k: Decimal('0.00') for k in (report_def.totals or [])}
        for row in rows_data:
            row_data = []
            for col in report_def.columns:
                val = row.get(col['key'], '')
                col_key = str(col.get('key', '')).lower()

                if isinstance(val, Decimal):
                    row_data.append(float(val))
                    if col['key'] in (report_def.totals or []):
                        running_totals[col['key']] += val
                elif hasattr(val, 'strftime'):
                    row_data.append(val.strftime('%d-%m-%Y'))
                elif (col_key == 'month' or col_key.endswith('_month')) and (isinstance(val, str) and len(val) == 7 and val[4] == '-'):
                    try:
                        row_data.append(datetime.strptime(val, '%Y-%m').strftime('%b %y'))
                    except ValueError:
                        row_data.append(val)
                else:
                    row_data.append(val if val is not None else '')
            ws.append(row_data)

        eff_totals = totals_dict if totals_dict else running_totals
        col_keys = [c['key'] for c in report_def.columns]
        has_pt_col = any(k in ('pass_through', 'operational_outflows') for k in col_keys)
        is_inflow = (filters.get('direction') == 'INFLOW' or slug in ('monthly-inflows',))
        is_special = slug in ('account-summary', 'fy-summary', 'routine-vs-addl', 'pass-through-summary', 'dynamic-transactions', 'budget-vs-actual', 'budget-utilisation')
        can_show_pt_reconciliation = False

        if report_def.totals and rows_data:
            sub_row = []
            for i, col in enumerate(report_def.columns):
                if i == 0:
                    lbl = "Total less Pass-Through" if can_show_pt_reconciliation else "Total"
                    sub_row.append(lbl)
                elif col['key'] in report_def.totals:
                    sub_row.append(float(eff_totals.get(col['key'], Decimal('0.00'))))
                else:
                    sub_row.append("")
            ws.append(sub_row)
            sub_idx = ws.max_row
            sub_fill = PatternFill(start_color='F1F5F9', end_color='F1F5F9', fill_type='solid')
            for c in range(1, len(sub_row) + 1):
                cell = ws.cell(row=sub_idx, column=c)
                cell.font = Font(name='Segoe UI', size=9.5, bold=True, color='0F172A')
                cell.fill = sub_fill
                cell.border = thin_border

            if can_show_pt_reconciliation:
                pt_row = []
                for i, col in enumerate(report_def.columns):
                    if i == 0:
                        pt_row.append("Add: Pass-Through Tfrs")
                    elif i == 1:
                        pt_row.append(float(pt_val))
                    else:
                        pt_row.append("")
                ws.append(pt_row)
                pt_idx = ws.max_row
                pt_fill = PatternFill(start_color='FEF3C7', end_color='FEF3C7', fill_type='solid')
                for c in range(1, len(pt_row) + 1):
                    cell = ws.cell(row=pt_idx, column=c)
                    cell.font = Font(name='Segoe UI', size=9.5, bold=True, color='B45309')
                    cell.fill = pt_fill
                    cell.border = thin_border

                gt_row = []
                for i, col in enumerate(report_def.columns):
                    if i == 0:
                        gt_row.append("Grand Total Incl. Pass-Through Txns")
                    elif col['key'] in report_def.totals:
                        gt_row.append(float(eff_totals.get(col['key'], Decimal('0.00')) + pt_val))
                    else:
                        gt_row.append("")
                ws.append(gt_row)
                gt_idx = ws.max_row
                gt_fill = PatternFill(start_color='E2E8F0', end_color='E2E8F0', fill_type='solid')
                for c in range(1, len(gt_row) + 1):
                    cell = ws.cell(row=gt_idx, column=c)
                    cell.font = Font(name='Segoe UI', size=10, bold=True, color='0F172A')
    if is_multi_fy and fy_sections and slug != 'dynamic-transactions':
        for sec in fy_sections:
            fy_obj = sec['fy']
            ws.append([])
            ws.append([f"--- FINANCIAL YEAR SECTION: {fy_obj.name} ---"])
            banner_idx = ws.max_row
            ws.cell(row=banner_idx, column=1).font = Font(name='Segoe UI', size=11, bold=True, color='0F172A')
            _append_generic_table(sec['dataset'], sec.get('totals'), sec.get('pass_through', Decimal('0.00')))

        if report_def.totals and grand_totals:
            ws.append([])
            ws.append(["--- MULTI-YEAR CONSOLIDATED GRAND TOTALS ---"])
            gt_banner_idx = ws.max_row
            ws.cell(row=gt_banner_idx, column=1).font = Font(name='Segoe UI', size=11, bold=True, color='0F172A')

            s_headers = ['Financial Year'] + [col['label'] for col in report_def.columns if col['key'] in report_def.totals]
            ws.append(s_headers)
            s_head_idx = ws.max_row
            for c in range(1, len(s_headers) + 1):
                cell = ws.cell(row=s_head_idx, column=c)
                cell.font = th_font
                cell.fill = th_fill
                cell.border = thin_border

            for sec in fy_sections:
                s_row = [sec['fy'].name]
                for col in report_def.columns:
                    if col['key'] in report_def.totals:
                        s_row.append(float(sec.get('totals', {}).get(col['key'], Decimal('0.00'))))
                ws.append(s_row)

            c_row = ['Combined All Years']
            for col in report_def.columns:
                if col['key'] in report_def.totals:
                    c_row.append(float(grand_totals.get(col['key'], Decimal('0.00'))))
            ws.append(c_row)
            c_idx = ws.max_row
            c_fill = PatternFill(start_color='E2E8F0', end_color='E2E8F0', fill_type='solid')
            for c in range(1, len(c_row) + 1):
                cell = ws.cell(row=c_idx, column=c)
                cell.font = Font(name='Segoe UI', size=10, bold=True, color='0F172A')
                cell.fill = c_fill
                cell.border = thin_border

    elif slug == 'dynamic-transactions':
        if fund_code == 'CPF':
            header_row = ['Date', 'Txn ID', 'Description & Type', 'Acct Head', 'Sub Fund', 'Sub Head', 'Amount (Rs)', 'Cohort', 'Package', 'Tour Operator', 'Pilgrim']
        elif fund_code == 'EWF':
            header_row = ['Date', 'Txn ID', 'Description & Type', 'Acct Head', 'Sub Fund', 'Sub Head', 'Amount (Rs)', 'Unit', 'Event', 'Venue']
        else:
            header_row = ['Date', 'Txn ID', 'Description & Type', 'Acct Head', 'Sub Fund', 'Sub Head', 'Amount (Rs)', 'Unit', 'Internal Sec']

        ws.append(header_row)
        header_idx = ws.max_row

        for c in range(1, len(header_row) + 1):
            cell = ws.cell(row=header_idx, column=c)
            cell.font = th_font
            cell.fill = th_fill
            cell.border = thin_border
            cell.alignment = Alignment(horizontal='center' if c in (1, 2) else 'left', vertical='center')

        ws.freeze_panes = ws.cell(row=header_idx + 1, column=1)

        normal_txns = [r for r in dataset if not r.get('pass_through')]
        pt_txns = [r for r in dataset if r.get('pass_through')]

        def _make_excel_row(r):
            d_str = r['date'].strftime('%d-%m-%Y') if hasattr(r.get('date'), 'strftime') else str(r.get('date', ''))
            tx_id = str(r.get('tx_id', ''))
            desc = f"[{r.get('direction', '')}] {'[PASS-THROUGH] ' if r.get('pass_through') else ''}{r.get('description', '')}"
            ah = str(r.get('account_head', ''))
            sf = str(r.get('major_head', ''))
            sh = str(r.get('sub_head', ''))
            amt = float(Decimal(str(r.get('amount') or 0)))

            base = [d_str, tx_id, desc, ah, sf, sh, amt]
            if fund_code == 'CPF':
                base.extend([str(r.get('cohort', '')), str(r.get('package', '')), str(r.get('tour_operator', '')), str(r.get('pilgrim', ''))])
            elif fund_code == 'EWF':
                base.extend([str(r.get('unit', '')), str(r.get('ceremony_event', '')), str(r.get('ceremony_venue', ''))])
            else:
                base.extend([str(r.get('unit', '')), str(r.get('internal_section', ''))])
            return base

        for r in normal_txns:
            ws.append(_make_excel_row(r))

        sub_row = ["Subtotal", "", "Total All Txns less Pass-Through", "", "", "", float(kpis.get('dt_normal_inflows', Decimal('0.00')) + kpis.get('dt_normal_outflows', Decimal('0.00')))]
        sub_row.extend([""] * (len(header_row) - len(sub_row)))
        ws.append(sub_row)
        sub_idx = ws.max_row
        for c in range(1, len(header_row) + 1):
            cell = ws.cell(row=sub_idx, column=c)
            cell.font = Font(name='Segoe UI', size=9.5, bold=True, color='0F172A')
            cell.fill = PatternFill(start_color='F1F5F9', end_color='F1F5F9', fill_type='solid')
            cell.border = thin_border

        if pt_txns:
            pt_head = ["[PASS-THROUGH]", "", "PASS-THROUGH TXNS (INTERNAL TFRS) — DETAILED INFLOWS & OUTFLOWS", "", "", "", ""]
            pt_head.extend([""] * (len(header_row) - len(pt_head)))
            ws.append(pt_head)
            pt_head_idx = ws.max_row
            for c in range(1, len(header_row) + 1):
                cell = ws.cell(row=pt_head_idx, column=c)
                cell.font = Font(name='Segoe UI', size=9.5, bold=True, color='B45309')
                cell.fill = PatternFill(start_color='FEF3C7', end_color='FEF3C7', fill_type='solid')
                cell.border = thin_border

            for r in pt_txns:
                ws.append(_make_excel_row(r))

            pt_tot_row = ["Pass-Through Total", "", "Total Pass-Through Tfrs", "", "", "", float(kpis.get('dt_pt_inflows', Decimal('0.00')) + kpis.get('dt_pt_outflows', Decimal('0.00')))]
            pt_tot_row.extend([""] * (len(header_row) - len(pt_tot_row)))
            ws.append(pt_tot_row)
            pt_tot_idx = ws.max_row
            for c in range(1, len(header_row) + 1):
                cell = ws.cell(row=pt_tot_idx, column=c)
                cell.font = Font(name='Segoe UI', size=9.5, bold=True, color='B45309')
                cell.fill = PatternFill(start_color='FEF3C7', end_color='FEF3C7', fill_type='solid')
                cell.border = thin_border

        gt_row = ["Grand Total", "", "Grand Total Incl. Pass-Through Txns", "", "", "", float(kpis.get('dt_total_inflows', Decimal('0.00')) + kpis.get('dt_total_outflows', Decimal('0.00')))]
        gt_row.extend([""] * (len(header_row) - len(gt_row)))
        ws.append(gt_row)
        gt_idx = ws.max_row
        for c in range(1, len(header_row) + 1):
            cell = ws.cell(row=gt_idx, column=c)
            cell.font = Font(name='Segoe UI', size=10, bold=True, color='0F172A')
            cell.fill = PatternFill(start_color='E2E8F0', end_color='E2E8F0', fill_type='solid')
            cell.border = thin_border

        bal_row = ["Fund Position", "", f"Opening Bal: Rs {kpis.get('opening_balance', 0):,.2f} | Net Movement: Rs {kpis.get('dt_net_movement', 0):,.2f}", "", "", "", float(kpis.get('closing_balance', Decimal('0.00')))]
        bal_row.extend([""] * (len(header_row) - len(bal_row)))
        ws.append(bal_row)
        bal_idx = ws.max_row
        for c in range(1, len(header_row) + 1):
            cell = ws.cell(row=bal_idx, column=c)
            cell.font = Font(name='Segoe UI', size=9.5, bold=True, color='0F172A')
            cell.fill = PatternFill(start_color='F8FAFC', end_color='F8FAFC', fill_type='solid')
            cell.border = thin_border
    else:
        pt_val = kpis.get('pt_total', Decimal('0.00')) if kpis else Decimal('0.00')
        _append_generic_table(dataset, totals_dict=None, pt_val=pt_val)

    if monthly_breakdown:
        ws.append([])
        ws.append(["DETAILED MONTHLY CASH FLOW & BALANCES"])
        title_idx = ws.max_row
        ws.cell(row=title_idx, column=1).font = Font(name='Segoe UI', size=11, bold=True, color='0F172A')

        m_headers = [
            'Month', 'Opening Balance', 
            'Operational Inflows (Excl PT)', 'Pass-Through Inflows', 'Total Inflows', 
            'Operational Outflows (Excl PT)', 'Pass-Through Outflows', 'Total Outflows', 
            'Net Movement', 'Closing Balance'
        ]
        ws.append(m_headers)
        h_idx = ws.max_row
        m_head_fill = PatternFill(start_color='E2E8F0', end_color='E2E8F0', fill_type='solid')
        for c in range(1, len(m_headers) + 1):
            cell = ws.cell(row=h_idx, column=c)
            cell.font = Font(name='Segoe UI', size=9.5, bold=True, color='0F172A')
            cell.fill = m_head_fill
            cell.border = thin_border
            if c > 1:
                cell.alignment = Alignment(horizontal='right')

        m_zebra_fill = PatternFill(start_color='F8FAFC', end_color='F8FAFC', fill_type='solid')
        display_in_millions = getattr(report_def, 'display_in_millions', False)

        for idx, row in enumerate(monthly_breakdown):
            m_str = row.get('month', '')
            if isinstance(m_str, str) and len(m_str) == 7 and m_str[4] == '-':
                try:
                    m_label = datetime.strptime(m_str, '%Y-%m').strftime('%b %y')
                except ValueError:
                    m_label = m_str
            else:
                m_label = str(m_str)

            ob_val = row.get('opening_balance', Decimal('0.00'))
            op_in_val = row.get('operational_inflows', row.get('inflows', Decimal('0.00')))
            pt_in_val = row.get('pass_through_inflows', Decimal('0.00'))
            tot_in_val = row.get('inflows', Decimal('0.00'))
            op_out_val = row.get('operational_outflows', row.get('outflows', Decimal('0.00')))
            pt_out_val = row.get('pass_through', Decimal('0.00'))
            tot_out_val = row.get('outflows', Decimal('0.00'))
            net_val = row.get('net_movement', Decimal('0.00'))
            cb_val = row.get('closing_balance', Decimal('0.00'))

            if display_in_millions:
                ob_num = float(ob_val / Decimal('1000000'))
                op_in_num = float(op_in_val / Decimal('1000000'))
                pt_in_num = float(pt_in_val / Decimal('1000000'))
                tot_in_num = float(tot_in_val / Decimal('1000000'))
                op_out_num = float(op_out_val / Decimal('1000000'))
                pt_out_num = float(pt_out_val / Decimal('1000000'))
                tot_out_num = float(tot_out_val / Decimal('1000000'))
                net_num = float(net_val / Decimal('1000000'))
                cb_num = float(cb_val / Decimal('1000000'))
            else:
                ob_num = float(ob_val)
                op_in_num = float(op_in_val)
                pt_in_num = float(pt_in_val)
                tot_in_num = float(tot_in_val)
                op_out_num = float(op_out_val)
                pt_out_num = float(pt_out_val)
                tot_out_num = float(tot_out_val)
                net_num = float(net_val)
                cb_num = float(cb_val)

            m_row = [m_label, ob_num, op_in_num, pt_in_num, tot_in_num, op_out_num, pt_out_num, tot_out_num, net_num, cb_num]
            ws.append(m_row)
            row_idx = ws.max_row
            row_fill = m_zebra_fill if (idx % 2 == 1) else None

            for c in range(1, len(m_row) + 1):
                cell = ws.cell(row=row_idx, column=c)
                cell.font = Font(name='Segoe UI', size=9, color='1E293B')
                if row_fill:
                    cell.fill = row_fill
                cell.border = thin_border
                if c > 1:
                    cell.alignment = Alignment(horizontal='right')
                    cell.number_format = '#,##0.00'
                    if c == 3:  # Operational Inflows
                        cell.font = Font(name='Segoe UI', size=9, bold=False, color='15803D')
                    elif c == 4:  # Pass-Through Inflows
                        cell.font = Font(name='Segoe UI', size=9, bold=False, color='B45309')
                    elif c == 5:  # Total Inflows
                        cell.font = Font(name='Segoe UI', size=9, bold=True, color='15803D')
                    elif c == 6:  # Operational Outflows
                        cell.font = Font(name='Segoe UI', size=9, bold=False, color='BE123C')
                    elif c == 7:  # Pass-Through Outflows
                        cell.font = Font(name='Segoe UI', size=9, bold=False, color='B45309')
                    elif c == 8:  # Total Outflows
                        cell.font = Font(name='Segoe UI', size=9, bold=True, color='BE123C')
                    elif c == 9:  # Net
                        cell.font = Font(name='Segoe UI', size=9, bold=True, color='15803D' if net_num >= 0 else 'BE123C')

        if monthly_totals:
            tot_op_in = monthly_totals.get('operational_inflows', monthly_totals.get('inflows', Decimal('0.00')))
            tot_pt_in = monthly_totals.get('pass_through_inflows', Decimal('0.00'))
            tot_in = monthly_totals.get('inflows', Decimal('0.00'))
            tot_op_out = monthly_totals.get('operational_outflows', Decimal('0.00'))
            tot_pt_out = monthly_totals.get('pass_through', Decimal('0.00'))
            tot_out = monthly_totals.get('outflows', Decimal('0.00'))
            tot_net = monthly_totals.get('net_movement', Decimal('0.00'))

            if display_in_millions:
                tot_op_in_num = float(tot_op_in / Decimal('1000000'))
                tot_pt_in_num = float(tot_pt_in / Decimal('1000000'))
                tot_in_num = float(tot_in / Decimal('1000000'))
                tot_op_out_num = float(tot_op_out / Decimal('1000000'))
                tot_pt_out_num = float(tot_pt_out / Decimal('1000000'))
                tot_out_num = float(tot_out / Decimal('1000000'))
                tot_net_num = float(tot_net / Decimal('1000000'))
            else:
                tot_op_in_num = float(tot_op_in)
                tot_pt_in_num = float(tot_pt_in)
                tot_in_num = float(tot_in)
                tot_op_out_num = float(tot_op_out)
                tot_pt_out_num = float(tot_pt_out)
                tot_out_num = float(tot_out)
                tot_net_num = float(tot_net)

            f_row = ['Full Period Totals', '', tot_op_in_num, tot_pt_in_num, tot_in_num, tot_op_out_num, tot_pt_out_num, tot_out_num, tot_net_num, '']
            ws.append(f_row)
            f_idx = ws.max_row
            f_fill = PatternFill(start_color='E2E8F0', end_color='E2E8F0', fill_type='solid')
            top_border = Border(
                top=Side(style='medium', color='0F172A'),
                bottom=Side(style='thin', color='CBD5E1'),
                left=Side(style='thin', color='CBD5E1'),
                right=Side(style='thin', color='CBD5E1')
            )
            for c in range(1, len(f_row) + 1):
                cell = ws.cell(row=f_idx, column=c)
                cell.font = Font(name='Segoe UI', size=9.5, bold=True, color='0F172A')
                cell.fill = f_fill
                cell.border = top_border
                if c in (3, 4, 5, 6, 7, 8, 9):
                    cell.alignment = Alignment(horizontal='right')
                    cell.number_format = '#,##0.00'
                    if c == 3:
                        cell.font = Font(name='Segoe UI', size=9.5, bold=False, color='15803D')
                    elif c == 4:
                        cell.font = Font(name='Segoe UI', size=9.5, bold=False, color='B45309')
                    elif c == 5:
                        cell.font = Font(name='Segoe UI', size=9.5, bold=True, color='15803D')
                    elif c == 6:
                        cell.font = Font(name='Segoe UI', size=9.5, bold=False, color='BE123C')
                    elif c == 7:
                        cell.font = Font(name='Segoe UI', size=9.5, bold=False, color='B45309')
                    elif c == 8:
                        cell.font = Font(name='Segoe UI', size=9.5, bold=True, color='BE123C')
                    elif c == 9:
                        cell.font = Font(name='Segoe UI', size=9.5, bold=True, color='15803D' if tot_net_num >= 0 else 'BE123C')

    # ---------------------------------------------------------
    # BOTTOM CONFIDENTIAL RUNNING FOOTER
    # ---------------------------------------------------------
    ws.append([])
    ws.append(["CONFIDENTIAL"])
    confd_bot_idx = ws.max_row
    ws.cell(row=confd_bot_idx, column=1).font = Font(name='Segoe UI', size=9, bold=True, color='BE123C')
    ws.cell(row=confd_bot_idx, column=1).alignment = Alignment(horizontal='center')

    # ---------------------------------------------------------
    # COLUMN WIDTHS
    # ---------------------------------------------------------
    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                if cell.value and len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except Exception:
                pass
        ws.column_dimensions[column].width = min(max_length + 3, 45)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()