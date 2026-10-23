from decimal import Decimal
from datetime import date
from django.contrib.auth.models import User
from django.test import TestCase

from core.models import Account, FinancialYear, AccountHead, Unit, InternalSection, Transaction
from reports.organisational_v2 import build_unit_summary, build_internal_section_summary, build_unit_section_summary


class OrganisationalAttributionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser('org-test', 'org@example.local', 'test-password')
        cls.account = Account.objects.create(code='TEST', name='Organisational Test Account')
        cls.fy = FinancialYear.objects.create(code='2026-27', name='FY 2026-27', start_date=date(2026, 7, 1), end_date=date(2027, 6, 30))
        cls.head = AccountHead.objects.create(account=cls.account, code='T-01', name='Test Outflow', head_type='OUTFLOW')
        cls.north_branch = Unit.objects.get(code='BR-NORTH')
        cls.acad = Unit.objects.get(code='ACAD')
        cls.evt = InternalSection.objects.get(code='EVT')
        cls.hqpm = InternalSection.objects.get(code='SEC')

    def _tx(self, number, amount):
        tx = Transaction.objects.create(
            transaction_number=number, account=self.account, financial_year=self.fy,
            account_head=self.head, transaction_date=date(2026, 8, 1), direction='OUTFLOW',
            amount=Decimal(amount), status='ACTIVE', created_by=self.user,
        )
        return tx

    def test_single_unit_and_section_attribution(self):
        tx = self._tx('TEST-TXN-001', '1000.00')
        tx.transaction_units.add(self.north_branch)
        tx.transaction_sections.add(self.evt)
        self.assertEqual(build_unit_summary({'account': self.account, 'financial_year': self.fy})[0]['amount'], Decimal('1000.00'))
        self.assertEqual(build_internal_section_summary({'account': self.account, 'financial_year': self.fy})[0]['amount'], Decimal('1000.00'))

    def test_multiple_units_and_sections_are_filterable(self):
        tx = self._tx('TEST-TXN-002', '2000.00')
        tx.transaction_units.add(self.acad, self.north_branch)
        tx.transaction_sections.add(self.evt, self.hqpm)
        rows = build_unit_section_summary({'account': self.account, 'financial_year': self.fy})
        self.assertEqual(len(rows), 4)

    def test_soft_deleted_transactions_are_excluded(self):
        tx = self._tx('TEST-TXN-003', '3000.00')
        tx.transaction_units.add(self.north_branch)
        tx.status = Transaction.Status.SOFT_DELETED
        tx.save()
        rows = build_unit_summary({'account': self.account, 'financial_year': self.fy})
        self.assertFalse(any(r['amount'] == Decimal('3000.00') for r in rows))
