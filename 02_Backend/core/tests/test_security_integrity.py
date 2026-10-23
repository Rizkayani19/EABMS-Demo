from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from core.models import (
    Account,
    AccountHead,
    AuditLog,
    FinancialYear,
    InflowType,
    Installation,
    OpeningBalance,
    OutflowNature,
    Reimbursement,
    Transaction,
    ReimbursementType,
)
from core.security_integrity import run_security_integrity_check


class SecurityIntegrityTests(TestCase):
    def setUp(self):
        installation = Installation.objects.create(installation_code="SEC-01", installation_name="Security Test")
        self.account = Account.objects.create(installation=installation, code="SEC", name="Security Account")
        self.other_account = Account.objects.create(installation=installation, code="OTR", name="Other Account")
        self.fy = FinancialYear.objects.create(
            code="2026-27", name="FY 2026-27", start_date=date(2026, 7, 1), end_date=date(2027, 6, 30)
        )
        self.head = AccountHead.objects.create(account=self.account, name="General", head_type="BOTH")
        self.other_head = AccountHead.objects.create(account=self.other_account, name="Other", head_type="BOTH")
        self.inflow_type = InflowType.objects.create(code="DIRECT", name="Direct")
        self.outflow_nature = OutflowNature.objects.create(code="ROUTINE", name="Routine")
        self.reimbursement_type = ReimbursementType.objects.create(code="REFUND", name="Refund")
        self.user = User.objects.create_user(username="security-test")

    def _transaction(self, direction, amount, account=None, audited=True):
        tx = Transaction(
            account=account or self.account,
            financial_year=self.fy,
            account_head=self.head if account is None or account == self.account else self.other_head,
            transaction_date=date(2026, 8, 1),
            direction=direction,
            amount=Decimal(amount),
            status=Transaction.Status.ACTIVE,
            inflow_type=self.inflow_type if direction == Transaction.Direction.INFLOW else None,
            outflow_nature=self.outflow_nature if direction == Transaction.Direction.OUTFLOW else None,
            created_by=self.user,
        )
        tx.save()
        if audited:
            AuditLog.objects.create(
                actor=self.user,
                account=tx.account,
                action="CREATE_TRANSACTION",
                model_name="Transaction",
                record_id=str(tx.id),
                record_repr=str(tx),
            )
        return tx

    def test_clean_security_check_passes_when_transaction_is_audited(self):
        self._transaction(Transaction.Direction.OUTFLOW, "1000")
        result = run_security_integrity_check(self.account, self.fy)
        self.assertEqual(result["status"], "PASS")

    def test_missing_transaction_audit_is_reported(self):
        self._transaction(Transaction.Direction.OUTFLOW, "1000", audited=False)
        result = run_security_integrity_check(self.account, self.fy)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(len(result["transaction_audit_issues"]), 1)

    def test_received_reimbursement_without_link_is_reported(self):
        outflow = self._transaction(Transaction.Direction.OUTFLOW, "5000")
        reimbursement = Reimbursement.objects.create(
            reimbursement_type=self.reimbursement_type,
            original_outflow=outflow,
            expected_amount=Decimal("5000"),
            received_amount=Decimal("2500"),
            expected_date=date(2026, 8, 15),
            source="Test Source",
            created_by=self.user,
        )
        result = run_security_integrity_check(self.account, self.fy)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(result["reimbursement_link_issues"])

    def test_confirmed_opening_balance_without_metadata_is_reported(self):
        OpeningBalance.objects.create(
            account=self.account,
            financial_year=self.fy,
            balance_amount=Decimal("1000"),
            is_confirmed=True,
        )
        result = run_security_integrity_check(self.account, self.fy)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(len(result["opening_balance_confirmation_issues"]), 1)
