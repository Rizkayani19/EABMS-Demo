from datetime import date

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.views.generic import TemplateView

from .balance_report_services import (
    build_account_head_report,
    build_sub_account_head_report,
    build_sub_fund_report,
)


class PresentBalanceReportBase(LoginRequiredMixin, TemplateView):
    template_name = "reports/present_balance_report.html"
    report_builder = None
    report_title = "Present Balance Report"

    def get_as_of(self):
        raw = self.request.GET.get("as_of", "").strip()
        if raw:
            try:
                return date.fromisoformat(raw)
            except ValueError:
                pass
        return date.today()

    def get(self, request, *args, **kwargs):
        account = request.account
        fy = request.fy
        as_of = self.get_as_of()
        if fy and as_of < fy.start_date:
            as_of = fy.start_date
        if fy and as_of > fy.end_date:
            as_of = fy.end_date
        report = self.report_builder(account, fy, as_of) if account and fy else {
            "level": self.report_title,
            "rows": [],
            "totals": {"opening_balance": 0, "total_inflows": 0, "total_outflows": 0, "difference": 0, "present_balance": 0},
            "fund_opening": 0,
            "fund_present": 0,
            "opening_reconciled": True,
        }
        return render(request, self.template_name, {
            "report": report,
            "report_title": self.report_title,
            "as_of": as_of,
            "account": account,
            "fy": fy,
        })


class PresentBalanceSubFundReportView(PresentBalanceReportBase):
    report_builder = staticmethod(build_sub_fund_report)
    report_title = "Present Balance — Sub Fund"


class PresentBalanceAccountHeadReportView(PresentBalanceReportBase):
    report_builder = staticmethod(build_account_head_report)
    report_title = "Present Balance — Account Head"


class PresentBalanceSubAccountHeadReportView(PresentBalanceReportBase):
    report_builder = staticmethod(build_sub_account_head_report)
    report_title = "Present Balance — Sub Account Head"
