from io import BytesIO

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views import View

from .future_budget_services import get_future_budget_summary
from .models import FutureBudget


def _budget(request, pk):
    return get_object_or_404(FutureBudget, pk=pk, account=request.account)


class FutureBudgetExcelExportView(LoginRequiredMixin, View):
    def get(self, request, pk):
        from openpyxl import Workbook

        budget = _budget(request, pk)
        summary = get_future_budget_summary(budget)
        wb = Workbook()
        ws = wb.active
        ws.title = 'Future Budget'
        ws.append(['Future Budget', str(budget)])
        ws.append(['Account', budget.account.name])
        ws.append(['Source FY', budget.source_fy.name])
        ws.append(['Target FY', budget.target_fy.name])
        ws.append([])
        head_col = 'Sub-Fund' if budget.budget_allocation_basis == 'SUB_FUND' else 'Account Head'
        ws.append([head_col, 'Previous Budget', 'Previous Actual', 'Routine', 'Continuing', 'Historical Additional', 'Known Changes', 'Personnel', 'One-Time', 'System Suggested', 'Management Proposed', 'Approved'])
        for line in budget.lines.select_related('account_head', 'major_head').order_by('major_head__code', 'account_head__name', 'pk'):
            name = line.account_head.name if line.account_head else (line.major_head.name if line.major_head else '—')
            ws.append([
                name,
                line.previous_budget,
                line.previous_actual,
                line.routine_amount,
                line.continuing_amount,
                line.addl_amount,
                line.known_change_amount,
                line.personnel_amount,
                line.onetime_amount,
                line.system_suggested,
                line.user_proposed,
                line.approved_amount,
            ])
        ws.append([])
        ws.append(['Summary', 'Amount'])
        ws.append(['Previous Actual', summary['previous_actual_total']])
        ws.append(['System Suggested', summary['system_suggested_total']])
        ws.append(['Management Proposed', summary['user_proposed_total']])
        ws.append(['Approved', summary['approved_total']])

        out = BytesIO()
        wb.save(out)
        response = HttpResponse(out.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="future_budget_{budget.pk}.xlsx"'
        return response


class FutureBudgetPDFExportView(LoginRequiredMixin, View):
    def get(self, request, pk):
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import landscape, A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

        budget = _budget(request, pk)
        summary = get_future_budget_summary(budget)
        out = BytesIO()
        doc = SimpleDocTemplate(out, pagesize=landscape(A4), rightMargin=24, leftMargin=24, topMargin=24, bottomMargin=24)
        styles = getSampleStyleSheet()
        story = [
            Paragraph('ABMS — Future Budget', styles['Title']),
            Paragraph(f'{budget.account.name} | {budget.source_fy.name} → {budget.target_fy.name}', styles['Normal']),
            Spacer(1, 12),
        ]
        head_col = 'Sub-Fund' if budget.budget_allocation_basis == 'SUB_FUND' else 'Account Head'
        data = [[head_col, 'Prev Actual', 'Routine', 'Continuing', 'Addl', 'Known', 'Personnel', 'One-Time', 'System Suggested', 'Proposed', 'Approved']]
        for line in budget.lines.select_related('account_head', 'major_head').order_by('major_head__code', 'account_head__name', 'pk'):
            name = line.account_head.name if line.account_head else (line.major_head.name if line.major_head else '—')
            data.append([
                name,
                f'{line.previous_actual:,.2f}', f'{line.routine_amount:,.2f}', f'{line.continuing_amount:,.2f}',
                f'{line.addl_amount:,.2f}', f'{line.known_change_amount:,.2f}', f'{line.personnel_amount:,.2f}',
                f'{line.onetime_amount:,.2f}', f'{line.system_suggested:,.2f}',
                f'{line.user_proposed:,.2f}' if line.user_proposed is not None else '—',
                f'{line.approved_amount:,.2f}' if line.approved_amount is not None else '—',
            ])
        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
        ]))
        story.extend([table, Spacer(1, 12), Paragraph(
            f"Previous Actual: Rs {summary['previous_actual_total']:,.2f} | "
            f"System Suggested: Rs {summary['system_suggested_total']:,.2f} | "
            f"Management Proposed: Rs {summary['user_proposed_total']:,.2f} | "
            f"Approved: Rs {summary['approved_total']:,.2f}", styles['Normal']
        )])
        doc.build(story)
        response = HttpResponse(out.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="future_budget_{budget.pk}.pdf"'
        return response


class FutureBudgetWordExportView(LoginRequiredMixin, View):
    def get(self, request, pk):
        from .budget_word_report import generate_budget_word_report
        budget = _budget(request, pk)
        data = generate_budget_word_report(budget)
        response = HttpResponse(
            data,
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        safe_acct = budget.account.code.replace(' ', '_')
        safe_fy = budget.target_fy.code.replace(' ', '_')
        response['Content-Disposition'] = f'attachment; filename="Budget_Analysis_{safe_acct}_{safe_fy}.docx"'
        return response

