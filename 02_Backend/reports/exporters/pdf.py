import io
from datetime import datetime
from decimal import Decimal

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas formatted according to formal Staff Duties (SD) standards:
    - Top Center: Page X of Y on Line 1, CONFD on Line 2
    - Bottom Center: CONFD
    - No distracting peripheral headers or footers.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        # Portrait A4 dimensions: width = 595.27, height = 841.89. Center is 297.64.

        # formal SD Top Header: Line 1 Page No (Centered), Line 2 CONFD (Centered)
        self.setFont("Helvetica", 7.5)
        self.setFillColor(colors.HexColor('#475569'))
        self.drawCentredString(297.64, 822, f"Page {self._pageNumber} of {page_count}")

        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor('#be123c'))
        self.drawCentredString(297.64, 811, "CONFIDENTIAL")

        # Top rule
        self.setStrokeColor(colors.HexColor('#cbd5e1'))
        self.setLineWidth(0.5)
        self.line(20, 804, 575.27, 804)

        # Bottom rule
        self.line(20, 30, 575.27, 30)

        # Corporate Bottom Footer: CONFIDENTIAL (Centered)
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor('#be123c'))
        self.drawCentredString(297.64, 18, "CONFIDENTIAL")

        self.restoreState()


def _pakistan_now_label():
    local_now = timezone.localtime(timezone.now(), timezone.get_fixed_timezone(5 * 60))
    return local_now.strftime('%d-%m-%Y %H:%M') + ' PKT (UTC+05:00)'


def export_to_pdf(report_def, dataset, filters, applied_filters=None, report_kpis=None, monthly_breakdown=None, monthly_totals=None, fy_sections=None, is_multi_fy=False, grand_totals=None):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20,
        rightMargin=20,
        topMargin=44,
        bottomMargin=36,
    )
    elements = []

    report_title = getattr(report_def, 'title', 'Report')
    report_slug = getattr(report_def, 'slug', '')
    report_desc = getattr(report_def, 'description', '')
    display_in_millions = getattr(report_def, 'display_in_millions', False)
    report_columns = getattr(report_def, 'columns', []) or []
    report_totals = getattr(report_def, 'totals', []) or []

    styles = getSampleStyleSheet()

    # Document Header Styles (Center aligned)
    title_style = ParagraphStyle(
        'DocMainTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=16,
        textColor=colors.HexColor('#0f172a'),
        alignment=1,  # Center
    )
    subtitle_style = ParagraphStyle(
        'DocReportTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=14,
        textColor=colors.HexColor('#047857'),
        alignment=1,  # Center
    )
    meta_style = ParagraphStyle(
        'DocMetaLine',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#334155'),
        alignment=1,  # Center
    )
    currency_notice_style = ParagraphStyle(
        'DocCurrencyNotice',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor('#64748b'),
        alignment=1,  # Center
    )

    # General Styles
    body_style = ParagraphStyle(
        'DocBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor('#334155'),
    )
    body_bold = ParagraphStyle(
        'DocBodyBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor('#0f172a'),
    )
    kpi_title = ParagraphStyle(
        'DocKPITitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7,
        leading=9,
        textColor=colors.HexColor('#475569'),
    )
    kpi_content = ParagraphStyle(
        'DocKPIContent',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7,
        leading=9.5,
        textColor=colors.HexColor('#0f172a'),
    )
    about_text = ParagraphStyle(
        'DocAboutText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor('#1e293b'),
    )
    section_head_style = ParagraphStyle(
        'SectionHeadStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor('#92400e'),
        alignment=1,  # Center
    )
    fy_banner_style = ParagraphStyle(
        'FYBannerStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#0f172a'),
    )

    # 1. Centered Document Header
    elements.append(Paragraph("EABMS — Enterprise Accounts & Business Management System", title_style))
    elements.append(Paragraph(f"Report: {report_title}", subtitle_style))

    acct_name = filters['account'].name if filters.get('account') else 'All Accts / Funds'
    fy_name = filters['financial_year'].name if filters.get('financial_year') else 'Active Fin Yr'
    selected_fys = filters.get('selected_fys', [])
    if is_multi_fy and selected_fys:
        fy_name = ", ".join(f.name for f in selected_fys)
    timestamp_str = _pakistan_now_label()
    elements.append(Paragraph(
        f"<b>Acct / Fund:</b> {acct_name} &nbsp;|&nbsp; <b>Fin Yr:</b> {fy_name} &nbsp;|&nbsp; <b>Gen:</b> {timestamp_str}",
        meta_style
    ))

    if display_in_millions:
        unit_notice = "(Amounts standardized in PKR Millions [Mn] unless otherwise indicated)"
    else:
        unit_notice = "(Amounts standardized in exact PKR [Rs] unless otherwise indicated)"
    elements.append(Paragraph(unit_notice, currency_notice_style))
    elements.append(Spacer(1, 6))

    # 2. "About This Report" Section
    if report_desc:
        desc_para = Paragraph(f"<b>About This Report:</b> {report_desc}", about_text)
        about_table = Table([[desc_para]], colWidths=[555.27])
        about_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f0f9ff')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#bae6fd')),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(about_table)
        elements.append(Spacer(1, 6))

    # 3. All Applied Filters Summary Block
    filters_para_parts = []
    if applied_filters:
        for f_item in applied_filters:
            filters_para_parts.append(f"<b>{f_item['label']}:</b> {f_item['value']}")
    else:
        if filters.get('account'):
            filters_para_parts.append(f"<b>Acct:</b> {filters['account'].name}")
        if filters.get('financial_year'):
            filters_para_parts.append(f"<b>Fin Yr:</b> {filters['financial_year'].name}")
        if filters.get('start_date') or filters.get('end_date'):
            s_str = filters['start_date'].strftime('%d-%m-%Y') if filters.get('start_date') else 'Start'
            e_str = filters['end_date'].strftime('%d-%m-%Y') if filters.get('end_date') else 'End'
            filters_para_parts.append(f"<b>Period:</b> {s_str} to {e_str}")
        else:
            filters_para_parts.append("<b>Period:</b> Full active Fin Yr")

    filter_text = " &nbsp;|&nbsp; ".join(filters_para_parts)
    filters_para = Paragraph(f"<b>Active Filters:</b> {filter_text}", body_style)
    filter_box = Table([[filters_para]], colWidths=[555.27])
    filter_box.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(filter_box)
    elements.append(Spacer(1, 6))

    # 4. Top KPI Summary Strip
    kpi_dict = report_kpis or {}
    if report_slug in ('dynamic-transactions', 'fy-summary', 'account-summary', 'pass-through-summary', 'monthly-trend', 'yoy-comparative', 'budget-vs-actual', 'budget-utilisation') or kpi_dict.get('is_financial_summary'):
        card1_txt = (
            f"<b>TOTAL RECORDS &amp; BALANCES</b><br/>"
            f"<font size='9'><b>{kpi_dict.get('total_records', 0)}</b> records</font><br/>"
            f"Opening: <b>Rs {kpi_dict.get('opening_balance_mn', Decimal('0.00'))} Mn</b><br/>"
            f"Closing: <b>Rs {kpi_dict.get('closing_balance_mn', Decimal('0.00'))} Mn</b>"
        )
        card2_txt = (
            f"<b>TOTAL INFLOWS excl Pass-Through (PKR Mn)</b><br/>"
            f"<font size='9' color='#15803d'><b>Rs {kpi_dict.get('dt_normal_inflows_mn', Decimal('0.00'))} Mn</b></font><br/>"
            f"Pass-Through Inflows: Rs {kpi_dict.get('dt_pt_inflows_mn', Decimal('0.00'))} Mn<br/>"
            f"<b>Grand Total incl PT: Rs {kpi_dict.get('dt_total_inflows_mn', Decimal('0.00'))} Mn</b>"
        )
        card3_txt = (
            f"<b>TOTAL OUTFLOWS excl Pass-Through (PKR Mn)</b><br/>"
            f"<font size='9' color='#be123c'><b>Rs {kpi_dict.get('dt_normal_outflows_mn', Decimal('0.00'))} Mn</b></font><br/>"
            f"Pass-Through Outflows: Rs {kpi_dict.get('dt_pt_outflows_mn', Decimal('0.00'))} Mn<br/>"
            f"<b>Grand Total incl PT: Rs {kpi_dict.get('dt_total_outflows_mn', Decimal('0.00'))} Mn</b>"
        )
        card4_txt = (
            f"<b>NET MOVEMENT excl Pass-Through (PKR Mn)</b><br/>"
            f"<font size='9'><b>Rs {kpi_dict.get('dt_normal_net_mn', Decimal('0.00'))} Mn</b></font><br/>"
            f"PT Tfrs: Rs {kpi_dict.get('dt_pt_transfers_mn', Decimal('0.00'))} Mn<br/>"
            f"<b>Grand Total Net incl PT: Rs {kpi_dict.get('dt_net_movement_mn', Decimal('0.00'))} Mn</b>"
        )
        card_w = 555.27 / 4.0
        kpi_table_data = [[
            Paragraph(card1_txt, kpi_content),
            Paragraph(card2_txt, kpi_content),
            Paragraph(card3_txt, kpi_content),
            Paragraph(card4_txt, kpi_content),
        ]]
        kpi_table = Table(kpi_table_data, colWidths=[card_w, card_w, card_w, card_w])
        kpi_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#ffffff')),
            ('BACKGROUND', (1, 0), (1, 0), colors.HexColor('#f0fdf4')),
            ('BACKGROUND', (2, 0), (2, 0), colors.HexColor('#fff1f2')),
            ('BACKGROUND', (3, 0), (3, 0), colors.HexColor('#f8fafc')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(kpi_table)
        elements.append(Spacer(1, 8))
    elif kpi_dict:
        total_exp = kpi_dict.get('report_total_mn')
        if total_exp is None or total_exp == Decimal('0.00'):
            total_exp = kpi_dict.get('excl_pt_total_mn', Decimal('0.00'))
        c1 = (
            f"<b>TOTAL RECORDS</b><br/>"
            f"<font size='9'><b>{kpi_dict.get('total_records', 0)}</b> records</font><br/>"
            f"Active Scope"
        )
        c2 = (
            f"<b>TOTAL EXPENDITURE / AMOUNT</b><br/>"
            f"<font size='9'><b>Rs {total_exp} Mn</b></font><br/>"
            f"Aggregated Scope Total"
        )
        c3 = (
            f"<b>FUND OPENING BALANCE</b><br/>"
            f"<font size='9'><b>Rs {kpi_dict.get('opening_balance_mn', Decimal('0.00'))} Mn</b></font><br/>"
            f"Starting Position"
        )
        c4 = (
            f"<b>FUND CLOSING BALANCE</b><br/>"
            f"<font size='9'><b>Rs {kpi_dict.get('closing_balance_mn', Decimal('0.00'))} Mn</b></font><br/>"
            f"Available Cash Position"
        )
        card_w = 555.27 / 4.0
        kpi_table_data = [[
            Paragraph(c1, kpi_content),
            Paragraph(c2, kpi_content),
            Paragraph(c3, kpi_content),
            Paragraph(c4, kpi_content),
        ]]
        kpi_table = Table(kpi_table_data, colWidths=[card_w, card_w, card_w, card_w])
        kpi_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#ffffff')),
            ('BACKGROUND', (1, 0), (1, 0), colors.HexColor('#f8fafc')),
            ('BACKGROUND', (2, 0), (2, 0), colors.HexColor('#f1f5f9')),
            ('BACKGROUND', (3, 0), (3, 0), colors.HexColor('#e2e8f0')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(kpi_table)
        elements.append(Spacer(1, 8))

    # Cell styles for data rows
    cell_style = ParagraphStyle(
        'CellRegular',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7,
        leading=9,
        textColor=colors.HexColor('#1e293b'),
    )
    cell_amt = ParagraphStyle(
        'CellAmount',
        parent=styles['Normal'],
        fontName='Courier-Bold',
        fontSize=7,
        leading=9,
        alignment=2,  # Right
        textColor=colors.HexColor('#0f172a'),
    )
    cell_amt_inflow = ParagraphStyle(
        'CellAmountInflow',
        parent=styles['Normal'],
        fontName='Courier-Bold',
        fontSize=7,
        leading=9,
        alignment=2,
        textColor=colors.HexColor('#15803d'),
    )
    cell_amt_outflow = ParagraphStyle(
        'CellAmountOutflow',
        parent=styles['Normal'],
        fontName='Courier-Bold',
        fontSize=7,
        leading=9,
        alignment=2,
        textColor=colors.HexColor('#be123c'),
    )
    th_style = ParagraphStyle(
        'TableHead',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7,
        leading=9,
        textColor=colors.HexColor('#0f172a'),
    )
    th_amt_style = ParagraphStyle(
        'TableHeadAmt',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7,
        leading=9,
        alignment=2,
        textColor=colors.HexColor('#0f172a'),
    )

    # 5. Data Tables (Multi-FY Section Aware or Single Table)
    fund_code = kpi_dict.get('fund_code', 'NGL')

    def _render_single_generic_table(rows_data, totals_dict=None, pt_amount=Decimal('0.00')):
        num_cols = len(report_columns) or 1
        col_w = 555.27 / num_cols

        headers = [Paragraph(f"<b>{col['label']}</b>", th_style) for col in report_columns]
        table_rows = [headers]
        running_totals = {k: Decimal('0.00') for k in report_totals}

        for row in rows_data:
            r_cells = []
            for col in report_columns:
                val = row.get(col['key'], '')
                col_key = str(col.get('key', '')).lower()

                if isinstance(val, Decimal):
                    if 'utilisation' in col_key or 'utilization' in col_key or col_key.endswith('_pct') or col_key == 'pct':
                        val_str = f"{val:.2f}%"
                        r_cells.append(Paragraph(val_str, cell_amt))
                    else:
                        if display_in_millions:
                            val_str = f"Rs {val / Decimal('1000000'):,.2f} Mn"
                        else:
                            val_str = f"Rs {val:,.2f}"
                        r_cells.append(Paragraph(val_str, cell_amt))
                    if col['key'] in report_totals:
                        running_totals[col['key']] += val
                elif hasattr(val, 'strftime'):
                    r_cells.append(Paragraph(val.strftime('%d-%m-%Y'), cell_style))
                elif (col_key == 'month' or col_key.endswith('_month')) and isinstance(val, str) and len(val) == 7 and val[4] == '-':
                    try:
                        m_fmt = datetime.strptime(val, '%Y-%m').strftime('%b %y')
                        r_cells.append(Paragraph(m_fmt, cell_style))
                    except ValueError:
                        r_cells.append(Paragraph(val, cell_style))
                else:
                    v_str = str(val) if val is not None else '—'
                    r_cells.append(Paragraph(v_str, cell_style))
            table_rows.append(r_cells)

        effective_totals = totals_dict if totals_dict else running_totals
        col_keys = [c['key'] for c in report_columns]
        has_pt_col = any(k in ('pass_through', 'operational_outflows') for k in col_keys)
        is_inflow = (filters.get('direction') == 'INFLOW' or report_slug in ('monthly-inflows',))
        is_special = report_slug in ('account-summary', 'fy-summary', 'routine-vs-addl', 'pass-through-summary', 'dynamic-transactions', 'budget-vs-actual', 'budget-utilisation')
        can_show_pt_reconciliation = False

        if report_totals and rows_data:
            # Subtotal row
            t_row = []
            for i, col in enumerate(report_columns):
                if i == 0:
                    lbl = "<b>Total less Pass-Through</b>" if can_show_pt_reconciliation else "<b>Total</b>"
                    t_row.append(Paragraph(lbl, body_bold))
                elif col['key'] in report_totals:
                    tot = effective_totals.get(col['key'], Decimal('0.00'))
                    tot_str = f"Rs {tot / Decimal('1000000'):,.2f} Mn" if display_in_millions else f"Rs {tot:,.2f}"
                    t_row.append(Paragraph(tot_str, cell_amt))
                else:
                    t_row.append(Paragraph("", cell_style))
            table_rows.append(t_row)

            if can_show_pt_reconciliation:
                pt_row = []
                for i, col in enumerate(report_columns):
                    if i == 0:
                        pt_row.append(Paragraph("<b>Add: Pass-Through Tfrs</b>", body_bold))
                    elif i == 1:
                        pt_str = f"Rs {pt_amount / Decimal('1000000'):,.2f} Mn" if display_in_millions else f"Rs {pt_amount:,.2f}"
                        pt_row.append(Paragraph(pt_str, cell_amt))
                    else:
                        pt_row.append(Paragraph("", cell_style))
                table_rows.append(pt_row)

                gt_row = []
                for i, col in enumerate(report_columns):
                    if i == 0:
                        gt_row.append(Paragraph("<b>Grand Total Incl. Pass-Through</b>", body_bold))
                    elif col['key'] in report_totals:
                        tot_incl = effective_totals.get(col['key'], Decimal('0.00')) + pt_amount
                        gt_str = f"Rs {tot_incl / Decimal('1000000'):,.2f} Mn" if display_in_millions else f"Rs {tot_incl:,.2f}"
                        gt_row.append(Paragraph(gt_str, cell_amt))
                    else:
                        gt_row.append(Paragraph("", cell_style))
                table_rows.append(gt_row)

        if not rows_data:
            table_rows.append([Paragraph("No data found for this section.", cell_style)] * num_cols)

        t = Table(table_rows, colWidths=[col_w] * num_cols, repeatRows=1)
        st = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -4 if (can_show_pt_reconciliation and report_totals and rows_data) else (-2 if report_totals and rows_data else -1)), [colors.white, colors.HexColor('#f8fafc')]),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ])
        if report_totals and rows_data:
            st.add('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e2e8f0'))
            st.add('LINEABOVE', (0, -1), (-1, -1), 1.5, colors.HexColor('#0f172a'))
        t.setStyle(st)
        return t

    if is_multi_fy and fy_sections and report_slug != 'dynamic-transactions':
        # Render each FY section as a separate distinct table with an executive header banner
        for sec in fy_sections:
            fy_obj = sec['fy']
            elements.append(Spacer(1, 6))
            banner_table = Table([[Paragraph(f"<b>FINANCIAL YEAR SECTION: {fy_obj.name}</b>", fy_banner_style)]], colWidths=[555.27])
            banner_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#e2e8f0')),
                ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#94a3b8')),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ]))
            elements.append(banner_table)
            elements.append(Spacer(1, 4))
            sec_table = _render_single_generic_table(sec['dataset'], sec.get('totals'), sec.get('pass_through', Decimal('0.00')))
            elements.append(sec_table)
            elements.append(Spacer(1, 10))

        # Overall Grand Summary Table for Multi-FY
        if report_totals and grand_totals:
            elements.append(Spacer(1, 4))
            gt_banner = Table([[Paragraph("<b>MULTI-YEAR CONSOLIDATED GRAND TOTALS</b>", fy_banner_style)]], colWidths=[555.27])
            gt_banner.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#cbd5e1')),
                ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#64748b')),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ]))
            elements.append(gt_banner)
            elements.append(Spacer(1, 4))

            summary_headers = [Paragraph("<b>Financial Year</b>", th_style)]
            for col in report_columns:
                if col['key'] in report_totals:
                    summary_headers.append(Paragraph(f"<b>{col['label']}</b>", th_amt_style))
            summary_rows = [summary_headers]

            for sec in fy_sections:
                s_row = [Paragraph(f"<b>{sec['fy'].name}</b>", cell_style)]
                for col in report_columns:
                    if col['key'] in report_totals:
                        amt = sec.get('totals', {}).get(col['key'], Decimal('0.00'))
                        amt_str = f"Rs {amt / Decimal('1000000'):,.2f} Mn" if display_in_millions else f"Rs {amt:,.2f}"
                        s_row.append(Paragraph(amt_str, cell_amt))
                summary_rows.append(s_row)

            # Combined total row
            c_row = [Paragraph("<b>Combined All Years</b>", body_bold)]
            for col in report_columns:
                if col['key'] in report_totals:
                    tot_amt = grand_totals.get(col['key'], Decimal('0.00'))
                    tot_str = f"Rs {tot_amt / Decimal('1000000'):,.2f} Mn" if display_in_millions else f"Rs {tot_amt:,.2f}"
                    c_row.append(Paragraph(tot_str, cell_amt))
            summary_rows.append(c_row)

            s_col_w = 555.27 / len(summary_headers)
            gt_summary_table = Table(summary_rows, colWidths=[s_col_w] * len(summary_headers))
            gt_summary_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f1f5f9')),
                ('LINEABOVE', (0, -1), (-1, -1), 1.5, colors.HexColor('#0f172a')),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ]))
            elements.append(gt_summary_table)

    elif report_slug == 'dynamic-transactions':
        # Column setup based on active fund:
        # Columns after Amount:
        # - NGL: Unit, Internal Section
        # - EWF: Cohort, Package, Tour Operator, Pilgrim
        # - CPF: Unit, Event, Venue
        if fund_code == 'CPF':
            col_widths = [50, 130, 90, 65, 55, 55, 55, 55.27]
            table_headers = [
                Paragraph("<b>Date & Txn ID</b>", th_style),
                Paragraph("<b>Description & Type</b>", th_style),
                Paragraph("<b>Acct Head</b>", th_style),
                Paragraph("<b>Amount (Rs)</b>", th_amt_style),
                Paragraph("<b>Cohort</b>", th_style),
                Paragraph("<b>Package</b>", th_style),
                Paragraph("<b>Tour Operator</b>", th_style),
                Paragraph("<b>Pilgrim</b>", th_style),
            ]
        elif fund_code == 'EWF':
            col_widths = [55, 140, 100, 70, 65, 65, 60.27]
            table_headers = [
                Paragraph("<b>Date & Txn ID</b>", th_style),
                Paragraph("<b>Description & Type</b>", th_style),
                Paragraph("<b>Acct Head</b>", th_style),
                Paragraph("<b>Amount (Rs)</b>", th_amt_style),
                Paragraph("<b>Unit</b>", th_style),
                Paragraph("<b>Event</b>", th_style),
                Paragraph("<b>Venue</b>", th_style),
            ]
        else:  # NGL and default
            col_widths = [60, 160, 110, 75, 75, 75.27]
            table_headers = [
                Paragraph("<b>Date & Txn ID</b>", th_style),
                Paragraph("<b>Description & Type</b>", th_style),
                Paragraph("<b>Acct Head</b>", th_style),
                Paragraph("<b>Amount (Rs)</b>", th_amt_style),
                Paragraph("<b>Unit</b>", th_style),
                Paragraph("<b>Internal Section</b>", th_style),
            ]

        data = [table_headers]
        num_cols = len(table_headers)

        # Segregate normal transactions and pass-through transactions
        normal_txns = [r for r in dataset if not r.get('pass_through')]
        pt_txns = [r for r in dataset if r.get('pass_through')]

        def _make_row_cells(row):
            d_str = row['date'].strftime('%d-%m-%Y') if hasattr(row.get('date'), 'strftime') else str(row.get('date', '—'))
            tx_id = str(row.get('tx_id', '—'))
            col1_html = f'<b>{d_str}</b><br/><font size="6" color="#475569">{tx_id}</font>'

            direction = row.get('direction', '')
            desc_text = str(row.get('description', '—'))
            is_pt = bool(row.get('pass_through'))

            badge_parts = []
            if direction == 'INFLOW':
                badge_parts.append('<font color="#15803d"><b>[INFLOW]</b></font>')
            elif direction == 'OUTFLOW':
                badge_parts.append('<font color="#be123c"><b>[OUTFLOW]</b></font>')
            if is_pt:
                badge_parts.append('<font color="#b45309"><b>[PASS-THROUGH]</b></font>')

            badge_str = " ".join(badge_parts) + " " if badge_parts else ""
            desc_html = f"{badge_str}{desc_text}"

            ah_name = str(row.get('account_head', '—'))
            sf_name = str(row.get('major_head', ''))
            sh_name = str(row.get('sub_head', ''))
            tier_info = []
            if sf_name and sf_name != '—':
                tier_info.append(f"Sub Fund: {sf_name}")
            if sh_name and sh_name != '—':
                tier_info.append(f"Sub Head: {sh_name}")
            tier_str = " • ".join(tier_info)
            sub_str = f'<br/><font size="6" color="#64748b">{tier_str}</font>' if tier_info else ''
            ah_html = f'<b>{ah_name}</b>{sub_str}'

            amt = Decimal(str(row.get('amount') or 0))
            amt_s = cell_amt_inflow if direction == 'INFLOW' else cell_amt_outflow
            amt_html = f"Rs {amt:,.2f}"

            base_cells = [
                Paragraph(col1_html, cell_style),
                Paragraph(desc_html, cell_style),
                Paragraph(ah_html, cell_style),
                Paragraph(amt_html, amt_s),
            ]

            if fund_code == 'CPF':
                base_cells.extend([
                    Paragraph(str(row.get('cohort', '—')), cell_style),
                    Paragraph(str(row.get('package', '—')), cell_style),
                    Paragraph(str(row.get('tour_operator', '—')), cell_style),
                    Paragraph(str(row.get('pilgrim', '—')), cell_style),
                ])
            elif fund_code == 'EWF':
                base_cells.extend([
                    Paragraph(str(row.get('unit', '—')), cell_style),
                    Paragraph(str(row.get('ceremony_event', '—')), cell_style),
                    Paragraph(str(row.get('ceremony_venue', '—')), cell_style),
                ])
            else:
                base_cells.extend([
                    Paragraph(str(row.get('unit', '—')), cell_style),
                    Paragraph(str(row.get('internal_section', '—')), cell_style),
                ])
            return base_cells

        # 1. Add normal transactions
        for row in normal_txns:
            data.append(_make_row_cells(row))

        # 2. Add Subtotal row (Excl. Pass-Through)
        norm_in = sum(Decimal(str(r.get('amount') or 0)) for r in normal_txns if r.get('direction') == 'INFLOW')
        norm_out = sum(Decimal(str(r.get('amount') or 0)) for r in normal_txns if r.get('direction') == 'OUTFLOW')
        sub_net = norm_in - norm_out

        sub_cells = [
            Paragraph("<b>Subtotal</b>", body_bold),
            Paragraph("<b>Total All Txns less Pass-Through</b>", body_bold),
            Paragraph(f"Inflows: Rs {norm_in:,.2f} | Outflows: Rs {norm_out:,.2f}", body_style),
            Paragraph(f"<b>Rs {norm_in + norm_out:,.2f}</b>", cell_amt),
        ]
        sub_cells.extend([Paragraph("", cell_style)] * (num_cols - 4))
        data.append(sub_cells)
        sub_row_idx = len(data) - 1

        # 3. If pass-through transactions exist, list them in detail!
        pt_section_start = None
        pt_section_end = None
        pt_in = sum(Decimal(str(r.get('amount') or 0)) for r in pt_txns if r.get('direction') == 'INFLOW')
        pt_out = sum(Decimal(str(r.get('amount') or 0)) for r in pt_txns if r.get('direction') == 'OUTFLOW')

        if pt_txns:
            pt_header_cells = [
                Paragraph("<b>PASS-THROUGH</b>", body_bold),
                Paragraph("<b>PASS-THROUGH TXNS (INTERNAL TFRS) — DETAILED INFLOWS &amp; OUTFLOWS</b>", section_head_style),
            ]
            pt_header_cells.extend([Paragraph("", cell_style)] * (num_cols - 2))
            data.append(pt_header_cells)
            pt_section_start = len(data) - 1

            for row in pt_txns:
                data.append(_make_row_cells(row))

            # Pass-Through Totals row
            pt_tot_cells = [
                Paragraph("<b>Pass-Through Total</b>", body_bold),
                Paragraph("<b>Total Pass-Through Tfrs</b>", body_bold),
                Paragraph(f"PT Inflows: Rs {pt_in:,.2f} | PT Outflows: Rs {pt_out:,.2f}", body_style),
                Paragraph(f"<b>Rs {pt_in + pt_out:,.2f}</b>", cell_amt),
            ]
            pt_tot_cells.extend([Paragraph("", cell_style)] * (num_cols - 4))
            data.append(pt_tot_cells)
            pt_section_end = len(data) - 1

        # 4. Grand Total row (Incl. Pass-Through)
        tot_in = norm_in + pt_in
        tot_out = norm_out + pt_out
        overall_net = tot_in - tot_out

        gt_cells = [
            Paragraph("<b>Grand Total</b>", body_bold),
            Paragraph("<b>Grand Total Incl. Pass-Through Txns</b>", body_bold),
            Paragraph(f"All Inflows: Rs {tot_in:,.2f} | All Outflows: Rs {tot_out:,.2f}", body_bold),
            Paragraph(f"<b>Rs {tot_in + tot_out:,.2f}</b>", cell_amt),
        ]
        gt_cells.extend([Paragraph("", cell_style)] * (num_cols - 4))
        data.append(gt_cells)
        gt_row_idx = len(data) - 1

        # 5. Opening and Closing Balance Reconciliation Row
        ob_val = kpi_dict.get('opening_balance', Decimal('0.00'))
        cb_val = kpi_dict.get('closing_balance', Decimal('0.00'))
        bal_cells = [
            Paragraph("<b>Fund Position</b>", body_bold),
            Paragraph(f"<b>Opening Bal:</b> Rs {ob_val:,.2f} &nbsp;|&nbsp; <b>Net Cash Movement:</b> Rs {overall_net:,.2f}", body_style),
            Paragraph(f"<b>Closing Available Balance:</b>", body_bold),
            Paragraph(f"<b>Rs {cb_val:,.2f}</b>", cell_amt),
        ]
        bal_cells.extend([Paragraph("", cell_style)] * (num_cols - 4))
        data.append(bal_cells)

        table = Table(data, colWidths=col_widths, repeatRows=1)
        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('ROWBACKGROUNDS', (0, 1), (-1, sub_row_idx - 1), [colors.white, colors.HexColor('#f8fafc')]),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            # Subtotal row styling
            ('BACKGROUND', (0, sub_row_idx), (-1, sub_row_idx), colors.HexColor('#f1f5f9')),
            ('LINEABOVE', (0, sub_row_idx), (-1, sub_row_idx), 1, colors.HexColor('#64748b')),
        ])

        if pt_txns and pt_section_start and pt_section_end:
            # Section header row
            style.add('BACKGROUND', (0, pt_section_start), (-1, pt_section_start), colors.HexColor('#fef3c7'))
            style.add('SPAN', (1, pt_section_start), (-1, pt_section_start))
            # Detailed PT rows zebra background
            style.add('ROWBACKGROUNDS', (0, pt_section_start + 1), (-1, pt_section_end - 1), [colors.HexColor('#fffbeb'), colors.HexColor('#fef3c7')])
            # PT total row
            style.add('BACKGROUND', (0, pt_section_end), (-1, pt_section_end), colors.HexColor('#fef3c7'))
            style.add('LINEABOVE', (0, pt_section_end), (-1, pt_section_end), 1, colors.HexColor('#d97706'))

        # Grand Total row
        style.add('BACKGROUND', (0, gt_row_idx), (-1, gt_row_idx), colors.HexColor('#e2e8f0'))
        style.add('LINEABOVE', (0, gt_row_idx), (-1, gt_row_idx), 1.5, colors.HexColor('#0f172a'))

        # Fund balance row
        style.add('BACKGROUND', (0, gt_row_idx + 1), (-1, gt_row_idx + 1), colors.HexColor('#f8fafc'))
        style.add('LINEABOVE', (0, gt_row_idx + 1), (-1, gt_row_idx + 1), 0.5, colors.HexColor('#94a3b8'))

        table.setStyle(style)
        elements.append(table)
    else:
        # Standard generic table for single FY
        pt_val = kpi_dict.get('pt_total', Decimal('0.00')) if kpi_dict else Decimal('0.00')
        table = _render_single_generic_table(dataset, totals_dict=None, pt_amount=pt_val)
        elements.append(table)

    if monthly_breakdown:
        elements.append(Spacer(1, 14))
        breakdown_title_style = ParagraphStyle(
            'BreakdownTitleStyle',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=9,
            leading=12,
            textColor=colors.HexColor('#0f172a'),
        )
        elements.append(Paragraph("<b>DETAILED MONTHLY CASH FLOW &amp; BALANCES</b>", breakdown_title_style))
        elements.append(Spacer(1, 4))

        m_cols_w = [37.27, 56.0, 58.0, 50.0, 58.0, 58.0, 50.0, 60.0, 62.0, 66.0]
        m_headers = [
            Paragraph("<b>Month</b>", th_style),
            Paragraph("<b>Opening Balance</b>", th_amt_style),
            Paragraph("<b>Op. Inflows (Excl PT)</b>", th_amt_style),
            Paragraph("<b>PT Inflows</b>", th_amt_style),
            Paragraph("<b>Total Inflows</b>", th_amt_style),
            Paragraph("<b>Op. Outflows (Excl PT)</b>", th_amt_style),
            Paragraph("<b>PT Outflows</b>", th_amt_style),
            Paragraph("<b>Total Outflows</b>", th_amt_style),
            Paragraph("<b>Net Movement</b>", th_amt_style),
            Paragraph("<b>Closing Balance</b>", th_amt_style),
        ]
        m_table_data = [m_headers]

        for m_row in monthly_breakdown:
            m_val = m_row.get("month", "")
            if isinstance(m_val, str) and len(m_val) == 7 and m_val[4] == "-":
                try:
                    m_label = datetime.strptime(m_val, "%Y-%m").strftime("%b %y")
                except ValueError:
                    m_label = m_val
            else:
                m_label = str(m_val)

            ob = m_row.get("opening_balance", Decimal("0.00"))
            op_in = m_row.get("operational_inflows", Decimal("0.00"))
            pt_in = m_row.get("pass_through_inflows", Decimal("0.00"))
            inf = m_row.get("inflows", Decimal("0.00"))
            op_out = m_row.get("operational_outflows", m_row.get("outflows", Decimal("0.00")))
            pt_out = m_row.get("pass_through", Decimal("0.00"))
            outf = m_row.get("outflows", Decimal("0.00"))
            net = m_row.get("net_movement", Decimal("0.00"))
            cb = m_row.get("closing_balance", Decimal("0.00"))

            if display_in_millions:
                ob_str = f"Rs {ob / Decimal('1000000'):,.2f} Mn"
                op_in_str = f"Rs {op_in / Decimal('1000000'):,.2f} Mn"
                pt_in_str = f"Rs {pt_in / Decimal('1000000'):,.2f} Mn"
                inf_str = f"Rs {inf / Decimal('1000000'):,.2f} Mn"
                op_out_str = f"Rs {op_out / Decimal('1000000'):,.2f} Mn"
                pt_out_str = f"Rs {pt_out / Decimal('1000000'):,.2f} Mn"
                outf_str = f"Rs {outf / Decimal('1000000'):,.2f} Mn"
                net_str = f"Rs {net / Decimal('1000000'):,.2f} Mn"
                cb_str = f"Rs {cb / Decimal('1000000'):,.2f} Mn"
            else:
                ob_str = f"Rs {ob:,.2f}"
                op_in_str = f"Rs {op_in:,.2f}"
                pt_in_str = f"Rs {pt_in:,.2f}"
                inf_str = f"Rs {inf:,.2f}"
                op_out_str = f"Rs {op_out:,.2f}"
                pt_out_str = f"Rs {pt_out:,.2f}"
                outf_str = f"Rs {outf:,.2f}"
                net_str = f"+Rs {net:,.2f}" if net >= Decimal("0.00") else f"-Rs {abs(net):,.2f}"
                cb_str = f"Rs {cb:,.2f}"

            net_style = cell_amt_inflow if net >= Decimal("0.00") else cell_amt_outflow

            m_table_data.append([
                Paragraph(f"<b>{m_label}</b>", cell_style),
                Paragraph(ob_str, cell_amt),
                Paragraph(op_in_str, cell_amt_inflow),
                Paragraph(pt_in_str, cell_amt),
                Paragraph(inf_str, cell_amt_inflow),
                Paragraph(op_out_str, cell_amt_outflow),
                Paragraph(pt_out_str, cell_amt),
                Paragraph(outf_str, cell_amt_outflow),
                Paragraph(net_str, net_style),
                Paragraph(cb_str, cell_amt),
            ])

        if monthly_totals:
            t_op_in = monthly_totals.get("operational_inflows", Decimal("0.00"))
            t_pt_in = monthly_totals.get("pass_through_inflows", Decimal("0.00"))
            t_inf = monthly_totals.get("inflows", Decimal("0.00"))
            t_op = monthly_totals.get("operational_outflows", Decimal("0.00"))
            t_pt = monthly_totals.get("pass_through", Decimal("0.00"))
            t_out = monthly_totals.get("outflows", Decimal("0.00"))
            t_net = monthly_totals.get("net_movement", Decimal("0.00"))

            if display_in_millions:
                t_op_in_str = f"Rs {t_op_in / Decimal('1000000'):,.2f} Mn"
                t_pt_in_str = f"Rs {t_pt_in / Decimal('1000000'):,.2f} Mn"
                t_inf_str = f"Rs {t_inf / Decimal('1000000'):,.2f} Mn"
                t_op_str = f"Rs {t_op / Decimal('1000000'):,.2f} Mn"
                t_pt_str = f"Rs {t_pt / Decimal('1000000'):,.2f} Mn"
                t_out_str = f"Rs {t_out / Decimal('1000000'):,.2f} Mn"
                t_net_str = f"Rs {t_net / Decimal('1000000'):,.2f} Mn"
            else:
                t_op_in_str = f"Rs {t_op_in:,.2f}"
                t_pt_in_str = f"Rs {t_pt_in:,.2f}"
                t_inf_str = f"Rs {t_inf:,.2f}"
                t_op_str = f"Rs {t_op:,.2f}"
                t_pt_str = f"Rs {t_pt:,.2f}"
                t_out_str = f"Rs {t_out:,.2f}"
                t_net_str = f"+Rs {t_net:,.2f}" if t_net >= Decimal("0.00") else f"-Rs {abs(t_net):,.2f}"

            t_net_style = cell_amt_inflow if t_net >= Decimal("0.00") else cell_amt_outflow

            m_table_data.append([
                Paragraph("<b>Full Period Totals</b>", body_bold),
                Paragraph("—", cell_amt),
                Paragraph(t_op_in_str, cell_amt_inflow),
                Paragraph(t_pt_in_str, cell_amt),
                Paragraph(t_inf_str, cell_amt_inflow),
                Paragraph(t_op_str, cell_amt_outflow),
                Paragraph(t_pt_str, cell_amt),
                Paragraph(t_out_str, cell_amt_outflow),
                Paragraph(t_net_str, t_net_style),
                Paragraph("—", cell_amt),
            ])

        m_table = Table(m_table_data, colWidths=m_cols_w, repeatRows=1)
        m_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -2 if monthly_totals else -1), [colors.white, colors.HexColor('#f8fafc')]),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ])
        if monthly_totals:
            m_style.add('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e2e8f0'))
            m_style.add('LINEABOVE', (0, -1), (-1, -1), 1.5, colors.HexColor('#0f172a'))

        m_table.setStyle(m_style)
        elements.append(m_table)

    doc.build(elements, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer.getvalue()
