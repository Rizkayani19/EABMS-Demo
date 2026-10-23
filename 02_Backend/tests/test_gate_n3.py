from datetime import date
from decimal import Decimal

from django.test import TestCase

from core.models import Account, AccountHead, FinancialYear, Transaction, Unit, InternalSection


class GateN3TransactionOrganisationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.account = Account.objects.create(code='N3', name='N3 Test Account')
        cls.fy = FinancialYear.objects.create(code='N3-2026', name='FY N3 2026', start_date=date(2026, 7, 1), end_date=date(2027, 6, 30), status=FinancialYear.Status.OPEN)
        cls.head = AccountHead.objects.create(account=cls.account, code='N3-H', name='N3 Test Head', head_type=AccountHead.HeadType.OUTFLOW)
        cls.unit_acad = Unit.objects.get_or_create(name='ACAD', defaults={'code': 'N3-ACAD'})[0]
        cls.unit_45 = Unit.objects.get_or_create(name='Northern Branch', defaults={'code': 'N3-U45'})[0]
        cls.evt = InternalSection.objects.get_or_create(name='EVT', defaults={'code': 'N3-EVT'})[0]
        cls.hqpm = InternalSection.objects.get_or_create(name='Security', defaults={'code': 'N3-HQPM'})[0]

    def make_transaction(self, amount=Decimal('1000.00')):
        return Transaction.objects.create(
            transaction_number=f'N3-{Transaction.objects.count()+1:06d}',
            account=self.account,
            financial_year=self.fy,
            account_head=self.head,
            transaction_date=date(2026, 8, 1),
            direction=Transaction.Direction.OUTFLOW,
            amount=amount
        )

    def test_single_unit_and_section_attribution(self):
        tx = self.make_transaction()
        tx.transaction_units.add(self.unit_acad)
        tx.transaction_sections.add(self.evt)
        self.assertEqual(tx.transaction_units.count(), 1)
        self.assertEqual(tx.transaction_sections.count(), 1)
        self.assertIn(self.unit_acad, tx.transaction_units.all())
        self.assertIn(self.evt, tx.transaction_sections.all())

    def test_multiple_units_and_sections_attribution(self):
        tx = self.make_transaction()
        tx.transaction_units.add(self.unit_acad, self.unit_45)
        tx.transaction_sections.add(self.evt, self.hqpm)
        self.assertEqual(tx.transaction_units.count(), 2)
        self.assertEqual(tx.transaction_sections.count(), 2)

    def test_filter_by_attributed_unit_and_section(self):
        tx1 = self.make_transaction(Decimal('500.00'))
        tx1.transaction_units.add(self.unit_acad)
        tx1.transaction_sections.add(self.evt)

        tx2 = self.make_transaction(Decimal('700.00'))
        tx2.transaction_units.add(self.unit_45)
        tx2.transaction_sections.add(self.hqpm)

        acad_txs = Transaction.objects.filter(transaction_units=self.unit_acad)
        self.assertEqual(acad_txs.count(), 1)
        self.assertEqual(acad_txs.first(), tx1)

        hqpm_txs = Transaction.objects.filter(transaction_sections=self.hqpm)
        self.assertEqual(hqpm_txs.count(), 1)
        self.assertEqual(hqpm_txs.first(), tx2)

