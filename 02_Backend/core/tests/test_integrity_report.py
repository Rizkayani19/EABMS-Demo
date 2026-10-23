from datetime import date
from decimal import Decimal

from django.test import TestCase

from core.integrity_report import build_integrity_report
from core.models import Account, FinancialYear, Installation, OpeningBalance, Transaction, AccountHead, InflowType


class IntegrityReportTests(TestCase):
    def setUp(self):
        installation = Installation.objects.create(
            installation_code="REPORT-01",
            installation_name="Integrity Report Test",
        )
        self.account = Account.objects.create(
            installation=installation,
            code="RPT",
            name="Report Account",
        )
        self.fy = FinancialYear.objects.create(
            code="2026-27",
            name="FY 2026-27",
            start_date=date(2026, 7, 1),
            end_date=date(2027, 6, 30),
        )
        self.head = AccountHead.objects.create(
            account=self.account,
            code="RPT-01",
            name="Report Head",
            head_type=AccountHead.HeadType.INFLOW,
        )
        self.inflow_type = InflowType.objects.create(code="DIRECT-RPT", name="Direct Report Inflow")

    def test_clean_report_passes(self):
        OpeningBalance.objects.create(
            account=self.account,
            financial_year=self.fy,
            balance_amount=Decimal("1000.00"),
        )
        Transaction.objects.create(
            transaction_number="RPT-IN-001",
            account=self.account,
            financial_year=self.fy,
            account_head=self.head,
            transaction_date=date(2026, 7, 5),
            direction=Transaction.Direction.INFLOW,
            amount=Decimal("500.00"),
            inflow_type=self.inflow_type,
            status=Transaction.Status.ACTIVE,
        )

        report = build_integrity_report(account=self.account, financial_year=self.fy)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["summary"]["total_exceptions"], 0)
        self.assertEqual(report["summary"]["reconciliations_checked"], 1)
        self.assertEqual(report["scope"]["account"], "RPT")
        self.assertEqual(report["scope"]["financial_year"], "2026-27")

    def test_report_fails_on_out_of_period_corruption(self):
        Transaction.objects.bulk_create([
            Transaction(
                transaction_number="RPT-BAD-001",
                account=self.account,
                financial_year=self.fy,
                account_head=self.head,
                transaction_date=date(2027, 7, 1),
                direction=Transaction.Direction.INFLOW,
                amount=Decimal("100.00"),
                inflow_type=self.inflow_type,
                status=Transaction.Status.ACTIVE,
            )
        ])

        report = build_integrity_report(account=self.account, financial_year=self.fy)
        self.assertEqual(report["status"], "FAIL")
        self.assertGreater(report["summary"]["total_exceptions"], 0)
        self.assertEqual(report["checks"]["financial_year_dates"]["status"], "FAIL")
