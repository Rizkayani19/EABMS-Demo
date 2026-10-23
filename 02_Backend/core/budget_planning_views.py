from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import render
from django.views import View

from core.budget_analysis_services import analyse_budget, variance_flags, build_existing_organisational_analysis
from core.future_budget_services import get_future_budget_summary
from core.future_budget_allocation_services import build_future_organisational_analysis
from core.models import FutureBudget, FinancialYear, UserProfile, Unit, InternalSection
from core.budget_reporting_export import export_budget_planning_workbook
from core.future_budget_management_export import export_future_budget_management_workbook


class BudgetPlanningReportView(LoginRequiredMixin, View):
    template_name = 'reports/budget_planning.html'

    def dispatch(self, request, *args, **kwargs):
        profile = getattr(request.user, 'profile', None)
        if not profile or profile.role not in (UserProfile.Role.ADMINISTRATOR, UserProfile.Role.MANAGEMENT):
            raise PermissionDenied('Budget planning reports are restricted to Management and Administrator.')
        return super().dispatch(request, *args, **kwargs)

    def _context(self, request):
        account = request.account
        source_fy = request.fy
        analysis = analyse_budget(account, source_fy) if account and source_fy else None
        flags = variance_flags(analysis) if analysis else []
        units = [v for v in request.GET.getlist('unit') if v]
        sections = [v for v in request.GET.getlist('section') if v]
        unit_master = Unit.objects.filter(is_active=True).order_by('display_order', 'name')
        section_master = InternalSection.objects.filter(is_active=True).order_by('display_order', 'name')
        existing_organisational_analysis = (
            build_existing_organisational_analysis(account, source_fy, units=units or None, internal_sections=sections or None)
            if account and source_fy else None
        )
        target_fy_id = request.GET.get('target_fy')
        target_fy = FinancialYear.objects.filter(pk=target_fy_id).first() if target_fy_id else None
        future_budget = None
        future_summary = None
        organisational_analysis = None
        if target_fy and account and source_fy:
            future_budget = FutureBudget.objects.filter(account=account, source_fy=source_fy, target_fy=target_fy).first()
            if future_budget:
                future_summary = get_future_budget_summary(future_budget)
                organisational_analysis = build_future_organisational_analysis(future_budget, units=units or None, internal_sections=sections or None)
        return {
            'account': account, 'source_fy': source_fy, 'target_fy': target_fy,
            'financial_years': FinancialYear.objects.order_by('-start_date'), 'analysis': analysis,
            'variance_flags': flags, 'units': units, 'sections': sections,
            'unit_master': unit_master, 'section_master': section_master,
            'existing_organisational_analysis': existing_organisational_analysis,
            'future_budget': future_budget, 'future_summary': future_summary,
            'organisational_analysis': organisational_analysis,
        }

    def get(self, request):
        return render(request, self.template_name, self._context(request))


class BudgetPlanningExcelExportView(LoginRequiredMixin, View):
    def dispatch(self, request, *args, **kwargs):
        profile = getattr(request.user, 'profile', None)
        if not profile or profile.role not in (UserProfile.Role.ADMINISTRATOR, UserProfile.Role.MANAGEMENT):
            raise PermissionDenied('Budget planning exports are restricted to Management and Administrator.')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        account = request.account
        source_fy = request.fy
        if not account or not source_fy:
            raise PermissionDenied('An active Account and Financial Year are required.')
        target_fy_id = request.GET.get('target_fy')
        target_fy = FinancialYear.objects.filter(pk=target_fy_id).first() if target_fy_id else None
        units = [v for v in request.GET.getlist('unit') if v]
        sections = [v for v in request.GET.getlist('section') if v]
        if target_fy:
            payload = export_future_budget_management_workbook(account, source_fy, target_fy, units=units or None, internal_sections=sections or None)
        else:
            payload = export_budget_planning_workbook(account, source_fy, target_fy, units=units or None, internal_sections=sections or None)
        filename = f'ABMS_Budget_Planning_{source_fy.name}'
        if target_fy:
            filename += f'_to_{target_fy.name}'
        if units:
            filename += '_Unit_Filtered'
        if sections:
            filename += '_Section_Filtered'
        response = HttpResponse(payload, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="{filename}.xlsx"'
        return response
