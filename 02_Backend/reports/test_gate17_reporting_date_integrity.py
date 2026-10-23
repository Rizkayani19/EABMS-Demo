from datetime import date
from decimal import Decimal

from django.test import TestCase

from core.models import Account, AccountHead, FinancialYear, Installation, OpeningBalance, Transaction
from reports.date_integrity import build_account_summary, build_monthly_inflows, build_monthly_outflows, build_monthly_trend
from reports.views import _get_filters_from_request


class Gate17ReportingDateIntegrityTests(TestCase):
    def setUp(self):
        installation = Installation.objects.create(
            installation_code="G17-TEST",
            installation_name="Gate 17 Test Installation",
        )
        self.account = Account.objects.create(
            installation=installation,
            code="G17",
            name="Gate 17 Account",
            is_active=True,
        )
        self.fy = FinancialYear.objects.create(
            code="2026-27-G17",
            name="FY 2026-27 G17",
            start_date=date(2026, 7, 1),
            end_date=date(2027, 6, 30),
            status=FinancialYear.Status.OPEN,
        )
        self.head = AccountHead.objects.create(
            account=self.account,
            code="G17-01",
            name="General",
            head_type=AccountHead.HeadType.BOTH,
        )
        OpeningBalance.objects.create(account=self.account, financial_year=self.fy, balance_amount=Decimal("1000.00"))

        self._tx(date(2026, 7, 5), Transaction.Direction.INFLOW, "100.00")
        self._tx(date(2026, 8, 10), Transaction.Direction.INFLOW, "250.00")
        self._tx(date(2026, 8, 20), Transaction.Direction.OUTFLOW, "75.00")
        self._tx(date(2026, 9, 2), Transaction.Direction.OUTFLOW, "125.00")

    def _tx(self, tx_date, direction, amount):
        return Transaction.objects.create(
            account=self.account,
            financial_year=self.fy,
            account_head=self.head,
            transaction_date=tx_date,
            direction=direction,
            amount=Decimal(amount),
            status=Transaction.Status.ACTIVE,
        )

    def _filters(self, start=None, end=None):
        return {
            "account": self.account,
            "financial_year": self.fy,
            **({"start_date": start} if start else {}),
            **({"end_date": end} if end else {}),
        }

    def test_monthly_reports_use_transaction_date(self):
        filters = self._filters(date(2026, 8, 1), date(2026, 8, 31))
        self.assertEqual(build_monthly_inflows(filters), [{
            "month": "2026-08",
            "operational_inflows": Decimal("250.00"),
            "pass_through": Decimal("0.00"),
            "amount": Decimal("250.00"),
        }])
        self.assertEqual(build_monthly_outflows(filters), [{
            "month": "2026-08",
            "operational_outflows": Decimal("75.00"),
            "pass_through": Decimal("0.00"),
            "amount": Decimal("75.00"),
        }])

    def test_monthly_trend_includes_zero_months_inside_selected_range(self):
        filters = self._filters(date(2026, 7, 1), date(2026, 9, 30))
        trend = build_monthly_trend(filters)
        self.assertEqual([row["month"] for row in trend], ["2026-07", "2026-08", "2026-09"])
        self.assertEqual(trend[0]["inflows"], Decimal("100.00"))
        self.assertEqual(trend[0]["outflows"], Decimal("0.00"))
        self.assertEqual(trend[1]["inflows"], Decimal("250.00"))
        self.assertEqual(trend[1]["outflows"], Decimal("75.00"))
        self.assertEqual(trend[2]["inflows"], Decimal("0.00"))
        self.assertEqual(trend[2]["outflows"], Decimal("125.00"))

    def test_account_summary_uses_period_opening_balance(self):
        filters = self._filters(date(2026, 8, 1), date(2026, 8, 31))
        row = build_account_summary(filters)[0]
        self.assertEqual(row["opening_balance"], Decimal("1100.00"))
        self.assertEqual(row["total_inflows"], Decimal("250.00"))
        self.assertEqual(row["total_outflows"], Decimal("75.00"))
        self.assertEqual(row["balance_available"], Decimal("1275.00"))

    def test_invalid_or_reversed_dates_are_report_errors(self):
        response = self.client.get(
            "/reports/monthly-trend/",
            {"start_date": "2026-09-30", "end_date": "2026-08-01"},
        )
        request = response.wsgi_request
        request.session["active_account_id"] = self.account.id
        request.session["active_fy_id"] = self.fy.id
        request.session.save()
        _, errors = _get_filters_from_request(request)
        self.assertTrue(errors)
        self.assertIn("Start Date cannot be later than End Date.", errors)

    def test_report_date_basis_is_not_created_at(self):
        filters = self._filters(date(2026, 7, 1), date(2026, 7, 31))
        rows = build_monthly_trend(filters)
        self.assertEqual(rows[0]["month"], "2026-07")
        self.assertEqual(rows[0]["inflows"], Decimal("100.00"))
        self.assertEqual(rows[0]["outflows"], Decimal("0.00"))
