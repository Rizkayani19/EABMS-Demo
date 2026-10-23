"""Formal Word (.docx) Budget Analysis and Proposed Budget Report Generator.

Directly generates authoritative Microsoft Word documents mirroring the official
formal staff-paper format:
'BUDGET ANALYSIS FY 2025-26 and PROPOSED BUDGET FY 2026-27'
Complete with confidentiality markings, multi-level numbering, styled variance tables,
Under-Command setup distribution, and annexures A through L.
"""

import io
from decimal import Decimal
from django.db.models import Sum, Q

import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn

from core.models import Transaction, BudgetLine, AccountHead
from core.future_budget_services import get_future_budget_summary

ZERO = Decimal('0.00')

def money_mn(val):
    d = (Decimal(str(val or 0)) / Decimal('1000000')).quantize(Decimal('0.01'))
    return f"{d:,.2f} Mn"

def money_rs(val):
    d = Decimal(str(val or 0)).quantize(Decimal('1'))
    return f"{d:,.0f}"

def _set_cell_shading(cell, color_hex):
    ns = nsdecls('w')
    shd = parse_xml(f'<w:shd {ns} w:fill="{color_hex}"/>')
    cell._tc.get_or_add_tcPr().append(shd)

def _set_table_borders(table):
    ns = nsdecls('w')
    borders = parse_xml(
        f'<w:tblBorders {ns}>'
        f'<w:top w:val="single" w:sz="6" w:space="0" w:color="A6B9D0"/>'
        f'<w:bottom w:val="single" w:sz="6" w:space="0" w:color="A6B9D0"/>'
        f'<w:insideH w:val="single" w:sz="4" w:space="0" w:color="D0D5DD"/>'
        f'<w:insideV w:val="single" w:sz="4" w:space="0" w:color="D0D5DD"/>'
        f'<w:left w:val="single" w:sz="6" w:space="0" w:color="A6B9D0"/>'
        f'<w:right w:val="single" w:sz="6" w:space="0" w:color="A6B9D0"/>'
        f'</w:tblBorders>'
    )
    table._tbl.tblPr.append(borders)

def generate_budget_word_report(future_budget):
    """Build the complete formal Word document for a FutureBudget instance."""
    doc = docx.Document()

    # Configure 1 inch page margins
    section = doc.sections[0]
    section.top_margin = Inches(1.0)
    section.bottom_margin = Inches(1.0)
    section.left_margin = Inches(1.0)
    section.right_margin = Inches(1.0)

    # Configure Header: CONFIDENTIAL
    header = section.header
    p_head = header.paragraphs[0]
    p_head.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_head = p_head.add_run('CONFIDENTIAL')
    r_head.bold = True
    r_head.font.size = Pt(11)
    r_head.font.underline = True

    # Configure Footer: CONFIDENTIAL
    footer = section.footer
    p_foot = footer.paragraphs[0]
    p_foot.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_foot = p_foot.add_run('CONFIDENTIAL')
    r_foot.bold = True
    r_foot.font.size = Pt(11)
    r_foot.font.underline = True

    # Set default document font to Arial 10.5 pt
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Arial'
    font.size = Pt(10.5)
    font.color.rgb = RGBColor(0x1F, 0x29, 0x37)

    account = future_budget.account
    source_fy = future_budget.source_fy
    target_fy = future_budget.target_fy

    # Fetch active transactions for source_fy
    txns = Transaction.objects.filter(
        account=account,
        financial_year=source_fy,
        status=Transaction.Status.ACTIVE,
        direction=Transaction.Direction.OUTFLOW,
    )

    # 1. Staff Header
    p_staff = doc.add_paragraph()
    p_staff.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p_staff.paragraph_format.space_after = Pt(2)
    r_staff1 = p_staff.add_run('Approved by: ____\n(Finance Committee)')
    r_staff1.bold = True
    r_staff1.font.color.rgb = RGBColor(0xC0, 0x00, 0x00)
    r_staff1.font.size = Pt(11)

    # Title
    p_title1 = doc.add_paragraph()
    p_title1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title1.paragraph_format.space_before = Pt(4)
    p_title1.paragraph_format.space_after = Pt(2)
    r_acct = p_title1.add_run(account.name.upper())
    r_acct.bold = True
    r_acct.font.underline = True
    r_acct.font.size = Pt(12)
    r_acct.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)

    p_title2 = doc.add_paragraph()
    p_title2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title2.paragraph_format.space_after = Pt(12)
    r_title = p_title2.add_run(f'BUDGET ANALYSIS {source_fy.name.upper()} & PROPOSED BUDGET {target_fy.name.upper()}')
    r_title.bold = True
    r_title.font.underline = True
    r_title.font.size = Pt(11.5)
    r_title.font.color.rgb = RGBColor(0x00, 0x20, 0x60)

    # Retrieve Financial Summary
    summary = get_future_budget_summary(future_budget)
    approved_budget_total = summary['previous_budget_total']
    actual_outflows_total = summary['previous_actual_total']
    diff_total = actual_outflows_total - approved_budget_total

    pt_txns = txns.filter(pass_through=True)
    pt_total = pt_txns.aggregate(s=Sum('amount'))['s'] or ZERO

    # SECTION 1: Overview
    p_sec1 = doc.add_paragraph()
    p_sec1.paragraph_format.space_before = Pt(6)
    p_sec1.paragraph_format.space_after = Pt(3)
    r_sec1 = p_sec1.add_run(f'1.  Overview – Budget {source_fy.name}')
    r_sec1.bold = True
    r_sec1.font.underline = True
    r_sec1.font.color.rgb = RGBColor(0x00, 0x20, 0x60)

    p_1a = doc.add_paragraph()
    p_1a.paragraph_format.left_indent = Inches(0.4)
    p_1a.paragraph_format.space_after = Pt(2)
    p_1a.add_run(f'a.  Fin Yr {source_fy.name} was the first formal budget year prepared for the {account.name} ({account.code}).')

    items_1 = [
        (f'b.  Approved {source_fy.name} Budget', f'Rs {money_mn(approved_budget_total)}'),
        ('c.  Actual Outflows', f'Rs {money_mn(actual_outflows_total)}'),
        ('d.  Diff (actual - budget)', f'Rs {money_mn(diff_total)}'),
        ('e.  Pass Through Transactions', f'Rs {money_mn(pt_total)}'),
    ]
    for label, val in items_1:
        p_row = doc.add_paragraph()
        p_row.paragraph_format.left_indent = Inches(0.4)
        p_row.paragraph_format.space_after = Pt(2)
        r_lbl = p_row.add_run(f'{label:<32} - ')
        r_lbl.bold = True
        r_val = p_row.add_run(val)
        r_val.bold = True

    p_1f = doc.add_paragraph()
    p_1f.paragraph_format.left_indent = Inches(0.4)
    p_1f.paragraph_format.space_after = Pt(2)
    p_1f.add_run(f'f.  Actual outflows were substantially higher than the approved budget. Detailed budget sheet for {source_fy.name} is att as Anx A.')

    p_1g = doc.add_paragraph()
    p_1g.paragraph_format.left_indent = Inches(0.4)
    p_1g.paragraph_format.space_after = Pt(8)
    p_1g.add_run('g.  Pass through transactions (money received from one acct and sent to another, with no net effect on resources) have been highlighted separately. Details at Anx B.')

    # SECTION 2: Analysis
    p_sec2 = doc.add_paragraph()
    p_sec2.paragraph_format.space_before = Pt(8)
    p_sec2.paragraph_format.space_after = Pt(4)
    r_sec2 = p_sec2.add_run(f'2.  Analysis – Budget {source_fy.name}.')
    r_sec2.bold = True
    r_sec2.font.underline = True
    r_sec2.font.color.rgb = RGBColor(0x00, 0x20, 0x60)
    p_sec2.add_run(' Analysis showed major variance in four primary budget heads:-')

    subhead_configs = [
        ('a.  Capacity Enhancement Project', 'Capacity Enhancement', 'Anx C', [
            ('1', 'Capacity Enhancement Project recorded the highest outlay. Significant expenditure was recouped from HQO.'),
            ('2', 'Portion identified as one-time additional expenditure. Detailed layout given as Anx C.'),
            ('3', 'Major additional expenditures include procurement, equipment, separation walls, and structural works.'),
        ]),
        ('b.  Fin Asst – Units', 'Fin Asst Units', 'Anx D', [
            ('1', 'Fin Asst – Units recorded second biggest portion in expenditures.'),
            ('2', 'One-time unusual expenditures detailed in layout given as Anx D.'),
        ]),
        ('c.  Salaries', 'Salaries', 'Anx E', [
            ('1', 'Contractual and expansion salaries detailed in layout given as Anx E.'),
            ('2', 'Major additional expenses include specialized groups and contractual staff.'),
        ]),
        ('d.  Office Misc Exp', 'Office Misc', 'Anx F', [
            ('1', 'Establishment and staff incentive expenses detailed in Anx F.'),
            ('2', 'Includes operational welfare packages, display shops, and incentive awards.'),
        ]),
    ]

    for label_sh, search_term, anx_ref, notes in subhead_configs:
        fb_line = future_budget.lines.filter(account_head__name__icontains=search_term).first()
        planned = fb_line.previous_budget if fb_line else ZERO
        exp = fb_line.previous_actual if fb_line else ZERO
        overspent = exp - planned
        pct_exp = (exp / actual_outflows_total * 100) if actual_outflows_total > ZERO else ZERO
        rtn = fb_line.routine_amount if fb_line else ZERO
        addl = (exp - rtn) if exp > rtn else ZERO

        p_sh = doc.add_paragraph()
        p_sh.paragraph_format.left_indent = Inches(0.2)
        p_sh.paragraph_format.space_before = Pt(6)
        p_sh.paragraph_format.space_after = Pt(2)
        r_sh = p_sh.add_run(label_sh)
        r_sh.bold = True

        tbl_sh = doc.add_table(rows=2, cols=6)
        tbl_sh.alignment = WD_TABLE_ALIGNMENT.CENTER
        _set_table_borders(tbl_sh)

        headers_sh = ['Planned', 'Exp', 'Overspent', '% of Exp', 'Routine', 'Addl']
        row0 = tbl_sh.rows[0]
        for idx, h in enumerate(headers_sh):
            c = row0.cells[idx]
            c.text = h
            p = c.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.runs[0].bold = True
            p.runs[0].font.size = Pt(9.5)
            _set_cell_shading(c, 'D9E1F2')

        row1 = tbl_sh.rows[1]
        vals_sh = [
            money_mn(planned),
            money_mn(exp),
            money_mn(overspent),
            f'{pct_exp:.0f} %',
            money_mn(rtn),
            money_mn(addl),
        ]
        for idx, v in enumerate(vals_sh):
            c = row1.cells[idx]
            c.text = v
            p = c.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.runs[0].font.size = Pt(9.5)
            if idx in (1, 2):
                p.runs[0].bold = True

        for num, text in notes:
            p_note = doc.add_paragraph()
            p_note.paragraph_format.left_indent = Inches(0.6)
            p_note.paragraph_format.space_after = Pt(1)
            p_note.add_run(f'({num})  {text}')

    # SECTION 3: UC Org / Setup wise Distr
    doc.add_page_break()
    p_sec3 = doc.add_paragraph()
    p_sec3.paragraph_format.space_before = Pt(6)
    p_sec3.paragraph_format.space_after = Pt(3)
    r_sec3 = p_sec3.add_run(f'3.  UC Org/ Setup wise Distr – Budget {source_fy.name}')
    r_sec3.bold = True
    r_sec3.font.underline = True
    r_sec3.font.color.rgb = RGBColor(0x00, 0x20, 0x60)

    # Dynamic UC unit calculation from active transactions
    u45_amt = txns.filter(description__iregex=r'(^|\W)(BR-NORTH|Northern Branch)(\W|$)').aggregate(s=Sum('amount'))['s'] or ZERO
    cmp_amt = txns.filter(description__iregex=r'(^|\W)BR-EAST(\W|$)').aggregate(s=Sum('amount'))['s'] or ZERO
    acad_amt = txns.filter(description__iregex=r'(^|\W)ACAD(\W|$)').aggregate(s=Sum('amount'))['s'] or ZERO
    mp29_amt = txns.filter(description__iregex=r'(^|\W)(BR-SOUTH|Southern Branch)(\W|$)').aggregate(s=Sum('amount'))['s'] or ZERO
    hqo_amt = txns.filter(description__iregex=r'(^|\W)HQO(\W|$)').aggregate(s=Sum('amount'))['s'] or ZERO

    uc_total = u45_amt + cmp_amt + acad_amt + mp29_amt + hqo_amt
    # If no unit transactions match (e.g. fresh/other account), fall back cleanly
    if uc_total > ZERO:
        u45_pct = f"{(u45_amt / uc_total * 100):.0f}%"
        cmp_pct = f"{(cmp_amt / uc_total * 100):.0f}%"
        acad_pct = f"{(acad_amt / uc_total * 100):.0f}%"
        mp29_pct = f"{(mp29_amt / uc_total * 100):.0f}%"
        hqo_pct = f"{(hqo_amt / uc_total * 100):.0f}%"
        tot_exp_pct = f"{(uc_total / actual_outflows_total * 100):.0f}% of exp" if actual_outflows_total > ZERO else "0% of exp"
    else:
        u45_pct, cmp_pct, acad_pct, mp29_pct, hqo_pct = "0%", "0%", "0%", "0%", "0%"
        tot_exp_pct = "0% of exp"

    unit_data = [
        ('Northern Branch\n(Anx G)', u45_amt, u45_pct),
        ('Eastern Branch\n(Anx H)', cmp_amt, cmp_pct),
        ('Training Academy\n(Anx I)', acad_amt, acad_pct),
        ('Southern Branch\n(Anx J)', mp29_amt, mp29_pct),
        ('Regional HQ\n(Anx K)', hqo_amt, hqo_pct),
        ('Total', uc_total, tot_exp_pct),
    ]

    p_3a = doc.add_paragraph()
    p_3a.paragraph_format.left_indent = Inches(0.4)
    p_3a.paragraph_format.space_after = Pt(4)
    p_3a.add_run(f'a.  {money_mn(uc_total)} were expended on branches. Branch-wise distribution and their percentage from total expended amount on them is as under:-')

    tbl_u = doc.add_table(rows=2, cols=6)
    tbl_u.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders(tbl_u)

    r0_u = tbl_u.rows[0]
    for idx, (col_name, _, _) in enumerate(unit_data):
        c = r0_u.cells[idx]
        c.text = col_name
        p = c.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.runs[0].bold = True
        p.runs[0].font.size = Pt(9.5)
        _set_cell_shading(c, 'D9E1F2')

    r1_u = tbl_u.rows[1]
    for idx, (_, amt, pct) in enumerate(unit_data):
        c = r1_u.cells[idx]
        c.text = f'{money_mn(amt)}\n({pct})'
        p = c.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.runs[0].font.size = Pt(9.5)
        if idx == 5:
            p.runs[0].bold = True

    # SECTION 4: Proposed Budget FY
    p_sec4 = doc.add_paragraph()
    p_sec4.paragraph_format.space_before = Pt(12)
    p_sec4.paragraph_format.space_after = Pt(3)
    r_sec4 = p_sec4.add_run(f'4.  Proposed Budget {target_fy.name}')
    r_sec4.bold = True
    r_sec4.font.underline = True
    r_sec4.font.color.rgb = RGBColor(0x00, 0x20, 0x60)

    p_4a = doc.add_paragraph()
    p_4a.paragraph_format.left_indent = Inches(0.4)
    p_4a.paragraph_format.space_after = Pt(3)
    p_4a.add_run(f'a.  Proposed Budget for the {target_fy.name} is calculated by segregating routine recurring exp from addl exp and on ground requirements.')

    tbl_prop = doc.add_table(rows=1, cols=4)
    tbl_prop.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders(tbl_prop)

    p_headers = ['Account Head', f'{source_fy.name}\nActual', f'{target_fy.name}\nSuggested', 'Change']
    for idx, h in enumerate(p_headers):
        c = tbl_prop.rows[0].cells[idx]
        c.text = h
        p = c.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.runs[0].bold = True
        p.runs[0].font.size = Pt(9.5)
        _set_cell_shading(c, 'D9E1F2')

    tot_act = ZERO
    tot_sugg = ZERO
    for line in future_budget.lines.select_related('account_head', 'major_head').order_by('-previous_actual'):
        r = tbl_prop.add_row()
        act = line.previous_actual
        sugg = line.system_suggested if line.approved_amount is None else line.approved_amount
        chg = sugg - act
        tot_act += act
        tot_sugg += sugg

        c0 = r.cells[0]
        c0.text = line.account_head.name if line.account_head else (line.major_head.name if line.major_head else '—')
        c0.paragraphs[0].runs[0].font.size = Pt(9)

        c1 = r.cells[1]
        c1.text = money_mn(act).replace(' Mn', '')
        c1.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
        c1.paragraphs[0].runs[0].font.size = Pt(9)

        c2 = r.cells[2]
        c2.text = money_mn(sugg).replace(' Mn', '')
        c2.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
        c2.paragraphs[0].runs[0].font.size = Pt(9)

        c3 = r.cells[3]
        prefix = '+' if chg > ZERO else ''
        c3.text = f"{prefix}{money_mn(chg).replace(' Mn', '')}"
        c3.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
        c3.paragraphs[0].runs[0].font.size = Pt(9)

    # Add TOTAL row
    r_tot = tbl_prop.add_row()
    r_tot.cells[0].text = 'TOTAL'
    r_tot.cells[0].paragraphs[0].runs[0].bold = True
    r_tot.cells[0].paragraphs[0].runs[0].font.size = Pt(9.5)

    r_tot.cells[1].text = money_mn(tot_act).replace(' Mn', '')
    r_tot.cells[1].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r_tot.cells[1].paragraphs[0].runs[0].bold = True
    r_tot.cells[1].paragraphs[0].runs[0].font.size = Pt(9.5)

    r_tot.cells[2].text = money_mn(tot_sugg).replace(' Mn', '')
    r_tot.cells[2].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r_tot.cells[2].paragraphs[0].runs[0].bold = True
    r_tot.cells[2].paragraphs[0].runs[0].font.size = Pt(9.5)

    tot_chg = tot_sugg - tot_act
    prefix = '+' if tot_chg > ZERO else ''
    r_tot.cells[3].text = f"{prefix}{money_mn(tot_chg).replace(' Mn', '')}"
    r_tot.cells[3].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r_tot.cells[3].paragraphs[0].runs[0].bold = True
    r_tot.cells[3].paragraphs[0].runs[0].font.size = Pt(9.5)
    for cell in r_tot.cells:
        _set_cell_shading(cell, 'F2F2F2')

    # Add Pass Through Transactions row (dynamic)
    # Projected pass-through defaults to the source-year actual
    proj_pt = pt_total
    pt_chg = proj_pt - pt_total
    prefix_pt = '+' if pt_chg > ZERO else ''

    r_pt = tbl_prop.add_row()
    r_pt.cells[0].text = 'Pass Through Transactions'
    r_pt.cells[0].paragraphs[0].runs[0].font.size = Pt(9)
    r_pt.cells[1].text = money_mn(pt_total).replace(' Mn', '')
    r_pt.cells[1].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r_pt.cells[1].paragraphs[0].runs[0].font.size = Pt(9)
    r_pt.cells[2].text = money_mn(proj_pt).replace(' Mn', '')
    r_pt.cells[2].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r_pt.cells[2].paragraphs[0].runs[0].font.size = Pt(9)
    r_pt.cells[3].text = f"{prefix_pt}{money_mn(pt_chg).replace(' Mn', '')}"
    r_pt.cells[3].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r_pt.cells[3].paragraphs[0].runs[0].font.size = Pt(9)

    # Inflows Narrative - calculate actual inflows for source FY
    inflow_txns = Transaction.objects.filter(
        account=account,
        financial_year=source_fy,
        status=Transaction.Status.ACTIVE,
        direction=Transaction.Direction.INFLOW,
    )
    actual_inflows_total = inflow_txns.aggregate(s=Sum('amount'))['s'] or ZERO

    p_4c = doc.add_paragraph()
    p_4c.paragraph_format.left_indent = Inches(0.4)
    p_4c.paragraph_format.space_before = Pt(6)
    p_4c.paragraph_format.space_after = Pt(2)

    p_4c.add_run(f'c.  Actual inflows for {source_fy.name} were {money_mn(actual_inflows_total)}.')
    p_4d = doc.add_paragraph()
    p_4d.paragraph_format.left_indent = Inches(0.4)
    p_4d.paragraph_format.space_before = Pt(4)
    p_4d.paragraph_format.space_after = Pt(6)
    net_variance = actual_inflows_total - tot_sugg
    status_txt = "surplus" if net_variance >= ZERO else "deficit"
    p_4d.add_run(f'd.  Net projected variance between source actual inflows and proposed outflows is {money_mn(abs(net_variance))} ({status_txt}), subject to opening balance bridging.')


    # SECTION 5: Recommendations
    p_sec5 = doc.add_paragraph()
    p_sec5.paragraph_format.space_before = Pt(8)
    p_sec5.paragraph_format.space_after = Pt(3)
    r_sec5 = p_sec5.add_run('5.  Recoms')
    r_sec5.bold = True
    r_sec5.font.underline = True
    r_sec5.font.color.rgb = RGBColor(0x00, 0x20, 0x60)

    recom_paras = [
        ('a.', 'Strict budgetary control and austerity measures are req to be implemented to keep the budget within prescribed limits as current fin model vis-a-vis aval fin resources does not appear to be viable for longer duration.'),
        ('b.', 'Capital expenditure across regional divisions has placed significant demand on corporate cash flows. To optimize budget utilization, the following is recommended: -'),
        ('  (1)', 'Divisional procurement should progressively transition from ad-hoc spot purchases to centralized bulk vendor agreements to secure enterprise pricing.'),
        ('  (2)', 'Increased reliance on divisional operational budgets should be emphasized with stricter monthly scrutiny. Monthly divisional variance statements must be obtained for complete visibility.'),
        ('  (3)', 'Commercial lease rationalization and shared regional facilities should be pursued to reduce recurring fixed overheads.'),
        ('  (4)', 'Oversight of operational budgets of regional offices and support divisions should be maintained on a monthly schedule.'),
        ('  (5)', 'Future capital enhancement proposals must be approved only after evaluating ROI and productivity impact of prior investments.'),
        ('  (6)', 'Inter-company allocations and vendor recoveries should continue to be processed systematically on schedule.'),
        ('c.', 'For FY 2026–27, routine discretionary allocation to a department or division should ordinarily remain within established quarterly ceilings.'),
        ('d.', 'Non-core facility renovation and recreational expenses should be met from dedicated employee welfare reserves.'),
        ('e.', 'Strict financial discipline and budgetary adherence across all corporate departments is required. Unplanned non-essential expenditure should be deferred.'),
        ('f.', 'Performance incentives and discretionary assistance must be subject to strict eligibility and budget affordability checks.'),
        ('g.', 'All expenditure proposals should be prioritized against core operational requirements before consideration of additional funding.'),
        ('h.', 'A monthly financial review should be instituted to identify emerging variances well in advance of fiscal quarter-end.'),
    ]
    for bullet, txt in recom_paras:
        p_rc = doc.add_paragraph()
        p_rc.paragraph_format.left_indent = Inches(0.4 if not bullet.startswith(' ') else 0.8)
        p_rc.paragraph_format.space_after = Pt(2)
        p_rc.add_run(f'{bullet.strip()}  {txt}')

    # ANNEXURES HELPER
    def _create_annexure_table(doc, anx_code, anx_title, columns, rows_data, total_amount):
        doc.add_page_break()
        p_lbl = doc.add_paragraph()
        p_lbl.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p_lbl.paragraph_format.space_after = Pt(2)
        r_l = p_lbl.add_run(anx_code)
        r_l.bold = True
        r_l.font.size = Pt(11)

        p_t = doc.add_paragraph()
        p_t.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_t.paragraph_format.space_after = Pt(6)
        r_t = p_t.add_run(anx_title)
        r_t.bold = True
        r_t.font.underline = True
        r_t.font.size = Pt(11)

        tbl = doc.add_table(rows=1, cols=len(columns))
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        _set_table_borders(tbl)

        for i, col in enumerate(columns):
            c = tbl.rows[0].cells[i]
            c.text = col
            p = c.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.runs[0].bold = True
            p.runs[0].font.size = Pt(9)
            _set_cell_shading(c, 'D9E1F2')

        for r_vals in rows_data:
            r = tbl.add_row()
            for i, val in enumerate(r_vals):
                c = r.cells[i]
                c.text = str(val)
                p = c.paragraphs[0]
                p.runs[0].font.size = Pt(8.5)
                if 'Amount' in columns[i]:
                    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT

        if total_amount is not None:
            r_tot = tbl.add_row()
            for c in r_tot.cells:
                _set_cell_shading(c, 'F2F2F2')
            r_tot.cells[0].text = 'Total'
            r_tot.cells[0].paragraphs[0].runs[0].bold = True
            r_tot.cells[0].paragraphs[0].runs[0].font.size = Pt(9)
            amt_idx = next(i for i, c in enumerate(columns) if 'Amount' in c)
            r_tot.cells[amt_idx].text = money_rs(total_amount)
            r_tot.cells[amt_idx].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
            r_tot.cells[amt_idx].paragraphs[0].runs[0].bold = True
            r_tot.cells[amt_idx].paragraphs[0].runs[0].font.size = Pt(9)

    # Anx B: Pass Through Transactions
    b_rows = []
    b_total = ZERO
    for t in pt_txns.order_by('transaction_date'):
        d_str = t.transaction_date.strftime('%d-%b-%y') if t.transaction_date else ''
        b_rows.append([d_str, t.description, money_rs(t.amount), t.remarks or 'Re-imbursed'])
        b_total += t.amount
    _create_annexure_table(
        doc, 'Anx B', 'PASS THROUGH TRANSACTIONS',
        ['Date', 'Detail', 'Amount (Rs)', 'Remarks'],
        b_rows, b_total
    )

    # Anx C: Capacity Enhancement Project - Additional Exp
    cap_txns = txns.filter(account_head__name__icontains='Capacity Enhancement').order_by('transaction_date')
    c_rows = []
    c_total = ZERO
    for t in cap_txns:
        d_str = t.transaction_date.strftime('%d-%b-%y') if t.transaction_date else ''
        c_rows.append([d_str, t.description, money_rs(t.amount)])
        c_total += t.amount
    _create_annexure_table(
        doc, 'Anx C', 'CAPACITY ENHANCEMENT PROJECT – ADDL EXP',
        ['Date', 'Detail', 'Amount (Rs)'],
        c_rows, c_total
    )

    # Anx D: Fin Asst Units - Additional Exp
    fa_txns = txns.filter(account_head__name__icontains='Fin Asst Units').order_by('transaction_date')
    d_rows = []
    d_total = ZERO
    for t in fa_txns:
        d_str = t.transaction_date.strftime('%d-%b-%y') if t.transaction_date else ''
        d_rows.append([d_str, t.description, money_rs(t.amount)])
        d_total += t.amount
    _create_annexure_table(
        doc, 'Anx D', 'FIN ASST UNITS – ADDL EXP',
        ['Date', 'Detail', 'Amount (Rs)'],
        d_rows, d_total
    )

    # Anx E: Salaries - Additional Exp
    sal_txns = txns.filter(account_head__name__icontains='Salaries').order_by('transaction_date')
    e_rows = []
    e_total = ZERO
    for t in sal_txns:
        d_str = t.transaction_date.strftime('%d-%b-%y') if t.transaction_date else ''
        e_rows.append([d_str, t.description, money_rs(t.amount)])
        e_total += t.amount
    _create_annexure_table(
        doc, 'Anx E', 'SALARIES – ADDL EXP',
        ['Date', 'Detail', 'Amount (Rs)'],
        e_rows, e_total
    )

    # Anx F: Office Misc Exp - Additional Exp
    misc_txns = txns.filter(account_head__name__icontains='Office Misc').order_by('transaction_date')
    f_rows = []
    f_total = ZERO
    for t in misc_txns:
        d_str = t.transaction_date.strftime('%d-%b-%y') if t.transaction_date else ''
        f_rows.append([d_str, t.description, money_rs(t.amount)])
        f_total += t.amount
    _create_annexure_table(
        doc, 'Anx F', 'OFFICE MISC EXP – ADDL EXP',
        ['Date', 'Detail', 'Amount (Rs)'],
        f_rows, f_total
    )

    # Anx G: Northern Branch - Total Exp
    u45_txns = txns.filter(description__icontains='Northern Branch').order_by('transaction_date')
    g_rows = []
    g_total = ZERO
    for t in u45_txns:
        d_str = t.transaction_date.strftime('%d-%b-%y') if t.transaction_date else ''
        g_rows.append([d_str, t.description, money_rs(t.amount), t.account_head.name if t.account_head else ''])
        g_total += t.amount
    _create_annexure_table(
        doc, 'Anx G', 'NORTHERN BRANCH – TOTAL EXP',
        ['Date', 'Detail', 'Amount (Rs)', 'Budget Head'],
        g_rows, g_total
    )

    # Anx H: BR-EAST Cen and School - Total Exp
    cmp_txns = txns.filter(Q(description__icontains='BR-EAST') | Q(description__icontains='Centre')).order_by('transaction_date')
    h_rows = []
    h_total = ZERO
    for t in cmp_txns:
        d_str = t.transaction_date.strftime('%d-%b-%y') if t.transaction_date else ''
        h_rows.append([d_str, t.description, money_rs(t.amount), t.account_head.name if t.account_head else ''])
        h_total += t.amount
    _create_annexure_table(
        doc, 'Anx H', 'EASTERN BRANCH – TOTAL EXP',
        ['Date', 'Detail', 'Amount (Rs)', 'Budget Head'],
        h_rows, h_total
    )

    # Anx J: ACAD - Total Exp
    acad_txns = txns.filter(description__icontains='ACAD').order_by('transaction_date')
    j_rows = []
    j_total = ZERO
    for t in acad_txns:
        d_str = t.transaction_date.strftime('%d-%b-%y') if t.transaction_date else ''
        j_rows.append([d_str, t.description, money_rs(t.amount), t.account_head.name if t.account_head else ''])
        j_total += t.amount
    _create_annexure_table(
        doc, 'Anx J', 'TRAINING ACADEMY – TOTAL EXP',
        ['Date', 'Detail', 'Amount (Rs)', 'Budget Head'],
        j_rows, j_total
    )

    # Anx K: Southern Branch - Total Exp
    mp29_txns = txns.filter(description__icontains='Southern Branch').order_by('transaction_date')
    k_rows = []
    k_total = ZERO
    for t in mp29_txns:
        d_str = t.transaction_date.strftime('%d-%b-%y') if t.transaction_date else ''
        k_rows.append([d_str, t.description, money_rs(t.amount), t.account_head.name if t.account_head else ''])
        k_total += t.amount
    _create_annexure_table(
        doc, 'Anx K', 'SOUTHERN BRANCH – TOTAL EXP',
        ['Date', 'Detail', 'Amount (Rs)', 'Budget Head'],
        k_rows, k_total
    )

    # Anx L: HQO - Total Exp
    hqo_txns = txns.filter(description__icontains='HQO').order_by('transaction_date')
    l_rows = []
    l_total = ZERO
    for t in hqo_txns:
        d_str = t.transaction_date.strftime('%d-%b-%y') if t.transaction_date else ''
        l_rows.append([d_str, t.description, money_rs(t.amount), t.account_head.name if t.account_head else ''])
        l_total += t.amount
    _create_annexure_table(
        doc, 'Anx L', 'REGIONAL HQ – TOTAL EXP',
        ['Date', 'Detail', 'Amount (Rs)', 'Budget Head'],
        l_rows, l_total
    )

    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()
