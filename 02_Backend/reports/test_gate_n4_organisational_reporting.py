from decimal import Decimal

from django.test import TestCase

from core.models import Account, AccountHead, FinancialYear, Transaction, Unit
from masters.models import InternalSection, TransactionOrganisationAllocation
from reports.organisational import build_organisational_transactions, build_unit_section_summary, build_unit_summary, build_internal_section_summary


class GateN4OrganisationalReportingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.account = Account.objects.create(code="N4", name="N4 Test Account")
        cls.fy = FinancialYear.objects.create(code="N4-2026", name="FY N4 2026", start_date="2026-07-01", end_date="2027-06-30", status=FinancialYear.Status.OPEN)
        cls.head = AccountHead.objects.create(account=cls.account, code="N4-H", name="N4 Test Head", head_type=AccountHead.HeadType.OUTFLOW)
        cls.acad = Unit.objects.get_or_create(name="ACAD", defaults={"code": "N4-ACAD"})[0]
        cls.north_branch = Unit.objects.get_or_create(name="Northern Branch", defaults={"code": "N4-BRN"})[0]
        cls.evt = InternalSection.objects.get_or_create(name="EVT", defaults={"code": "N4-EVT"})[0]
        cls.hqpm = InternalSection.objects.get_or_create(name="Security", defaults={"code": "N4-HQPM"})[0]

    def make_tx(self, number, amount):
        return Transaction.objects.create(transaction_number=number, account=self.account, financial_year=self.fy, account_head=self.head, transaction_date="2026-08-01", direction=Transaction.Direction.OUTFLOW, amount=amount, status=Transaction.Status.ACTIVE)

    def test_unit_summary_uses_allocated_amount_not_transaction_amount(self):
        tx = self.make_tx("N4-001", Decimal("1000.00")); TransactionOrganisationAllocation.objects.create(transaction=tx, unit=self.acad, internal_section=self.evt, allocated_amount=Decimal("600.00")); TransactionOrganisationAllocation.objects.create(transaction=tx, unit=self.north_branch, internal_section=self.evt, allocated_amount=Decimal("400.00"))
        rows = build_unit_summary({"account": self.account, "financial_year": self.fy}); amounts = {r["unit"]: r["amount"] for r in rows}
        self.assertEqual(amounts["ACAD"], Decimal("600.00")); self.assertEqual(amounts["Northern Branch"], Decimal("400.00")); self.assertEqual(sum(amounts.values()), Decimal("1000.00"))

    def test_combined_unit_section_is_explicit_and_does_not_double_count(self):
        tx = self.make_tx("N4-002", Decimal("1000.00"));
        for unit, section, amount in [(self.acad, self.evt, Decimal("600.00")), (self.north_branch, self.evt, Decimal("250.00")), (self.north_branch, self.hqpm, Decimal("150.00"))]: TransactionOrganisationAllocation.objects.create(transaction=tx, unit=unit, internal_section=section, allocated_amount=amount)
        rows = build_unit_section_summary({"account": self.account, "financial_year": self.fy}); lookup = {(r["unit"], r["internal_section"]): r["amount"] for r in rows}
        self.assertEqual(lookup[("ACAD", "EVT")], Decimal("600.00")); self.assertEqual(lookup[("Northern Branch", "EVT")], Decimal("250.00")); self.assertEqual(lookup[("Northern Branch", "Security")], Decimal("150.00")); self.assertEqual(sum(r["amount"] for r in rows), Decimal("1000.00"))

    def test_section_filter_selects_allocations_even_when_transaction_has_multiple_units(self):
        tx = self.make_tx("N4-003", Decimal("1000.00")); TransactionOrganisationAllocation.objects.create(transaction=tx, unit=self.acad, internal_section=self.evt, allocated_amount=Decimal("700.00")); TransactionOrganisationAllocation.objects.create(transaction=tx, unit=self.north_branch, internal_section=self.hqpm, allocated_amount=Decimal("300.00"))
        rows = build_organisational_transactions({"account": self.account, "financial_year": self.fy, "internal_section_ids": [self.evt.pk]}); self.assertEqual(len(rows), 1); self.assertEqual(rows[0]["amount"], Decimal("700.00")); self.assertEqual(rows[0]["internal_section"], "EVT")

    def test_unit_filter_selects_only_requested_units(self):
        tx = self.make_tx("N4-004", Decimal("1000.00")); TransactionOrganisationAllocation.objects.create(transaction=tx, unit=self.acad, internal_section=self.evt, allocated_amount=Decimal("700.00")); TransactionOrganisationAllocation.objects.create(transaction=tx, unit=self.north_branch, internal_section=self.evt, allocated_amount=Decimal("300.00"))
        rows = build_organisational_transactions({"account": self.account, "financial_year": self.fy, "unit_ids": [self.acad.pk]}); self.assertEqual(len(rows), 1); self.assertEqual(rows[0]["unit"], "ACAD"); self.assertEqual(rows[0]["amount"], Decimal("700.00"))

    def test_section_summary_uses_allocation_grain(self):
        tx = self.make_tx("N4-005", Decimal("1000.00")); TransactionOrganisationAllocation.objects.create(transaction=tx, unit=self.acad, internal_section=self.evt, allocated_amount=Decimal("800.00")); TransactionOrganisationAllocation.objects.create(transaction=tx, unit=self.north_branch, internal_section=self.hqpm, allocated_amount=Decimal("200.00"))
        rows = build_internal_section_summary({"account": self.account, "financial_year": self.fy}); amounts = {r["internal_section"]: r["amount"] for r in rows}
        self.assertEqual(amounts["EVT"], Decimal("800.00")); self.assertEqual(amounts["Security"], Decimal("200.00"))
