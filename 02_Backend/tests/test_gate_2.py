from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import date
from core.models import (
    Installation, Account, FinancialYear, AccountHead, BudgetType, 
    Transaction, Reimbursement, ReimbursementType, OpeningBalance,
    OutflowNature
)
from core.services import (
    get_total_actual_inflows, get_total_actual_outflows, get_balance_available,
    get_pass_through_outflows, get_reimbursement_summary, get_period_summary
)

class Gate2FinancialCoreTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='clerk', password='123')
        self.inst = Installation.objects.create(installation_code='INST-01', installation_name='Main')
        self.ngl = Account.objects.create(installation=self.inst, code='NGL', name='NGL Fund')
        self.cpf = Account.objects.create(installation=self.inst, code='CPF', name='CPF Fund')
        
        self.fy26 = FinancialYear.objects.create(
            code='2026-27', name='FY 2026-27', start_date=date(2026, 7, 1), end_date=date(2027, 6, 30), status='OPEN'
        )
        self.fy25 = FinancialYear.objects.create(
            code='2025-26', name='FY 2025-26', start_date=date(2025, 7, 1), end_date=date(2026, 6, 30), status='CLOSED'
        )

        self.head_ngl = AccountHead.objects.create(account=self.ngl, name='Utility NGL', code='Q-01')
        self.head_cpf = AccountHead.objects.create(account=self.cpf, name='Utility CPF', code='P-01')
        
        self.reimb_type = ReimbursementType.objects.create(code='GENERAL', name='General')
        self.outflow_nature = OutflowNature.objects.create(code='ROUTINE', name='Routine')

    def test_opening_balance(self):
        ob = OpeningBalance.objects.create(
            account=self.ngl,
            financial_year=self.fy26,
            balance_amount=Decimal('20.00'),
            reference='OB-001',
            remarks='Initial OB'
        )
        self.assertEqual(get_balance_available(self.ngl, self.fy26), Decimal('20.00'))

    def test_inflows_and_outflows_state(self):
        ob = OpeningBalance.objects.create(account=self.ngl, financial_year=self.fy26, balance_amount=Decimal('20.00'))
        
        # Active Inflow
        Transaction.objects.create(
            account=self.ngl, financial_year=self.fy26, account_head=self.head_ngl,
            transaction_date=date(2026, 8, 1), direction=Transaction.Direction.INFLOW,
            amount=Decimal('10.00'), status=Transaction.Status.ACTIVE
        )
        # Draft Inflow (Should not affect balance)
        Transaction.objects.create(
            account=self.ngl, financial_year=self.fy26, account_head=self.head_ngl,
            transaction_date=date(2026, 8, 2), direction=Transaction.Direction.INFLOW,
            amount=Decimal('100.00'), status=Transaction.Status.DRAFT
        )
        # Cancelled Inflow (Should not affect balance)
        Transaction.objects.create(
            account=self.ngl, financial_year=self.fy26, account_head=self.head_ngl,
            transaction_date=date(2026, 8, 3), direction=Transaction.Direction.INFLOW,
            amount=Decimal('200.00'), status=Transaction.Status.CANCELLED
        )
        
        # Active Outflow
        Transaction.objects.create(
            account=self.ngl, financial_year=self.fy26, account_head=self.head_ngl,
            transaction_date=date(2026, 8, 4), direction=Transaction.Direction.OUTFLOW,
            amount=Decimal('18.00'), status=Transaction.Status.ACTIVE
        )

        self.assertEqual(get_balance_available(self.ngl, self.fy26), Decimal('12.00')) # 20 + 10 - 18 = 12

    def test_account_isolation(self):
        # CPF transactions should not affect NGL
        Transaction.objects.create(
            account=self.cpf, financial_year=self.fy26, account_head=self.head_cpf,
            transaction_date=date(2026, 8, 1), direction=Transaction.Direction.INFLOW,
            amount=Decimal('500.00'), status=Transaction.Status.ACTIVE
        )
        self.assertEqual(get_balance_available(self.ngl, self.fy26), Decimal('0.00'))

    def test_fy_isolation(self):
        # FY25 transactions should not affect FY26
        Transaction.objects.create(
            account=self.ngl, financial_year=self.fy25, account_head=self.head_ngl,
            transaction_date=date(2025, 8, 1), direction=Transaction.Direction.INFLOW,
            amount=Decimal('500.00'), status=Transaction.Status.ACTIVE,
            is_historical=True
        )
        self.assertEqual(get_balance_available(self.ngl, self.fy26), Decimal('0.00'))

    def test_reimbursement_logic(self):
        outflow = Transaction.objects.create(
            account=self.ngl, financial_year=self.fy26, account_head=self.head_ngl,
            transaction_date=date(2026, 8, 1), direction=Transaction.Direction.OUTFLOW,
            amount=Decimal('10.00'), status=Transaction.Status.ACTIVE
        )
        
        reimb = Reimbursement.objects.create(
            reimbursement_type=self.reimb_type,
            original_outflow=outflow,
            expected_amount=Decimal('10.00'),
            expected_date=date(2026, 8, 10),
            status=Reimbursement.Status.PARTIALLY_RECEIVED
        )
        
        # Receive 6
        inflow = Transaction.objects.create(
            account=self.ngl, financial_year=self.fy26, account_head=self.head_ngl,
            transaction_date=date(2026, 8, 12), direction=Transaction.Direction.INFLOW,
            amount=Decimal('6.00'), status=Transaction.Status.ACTIVE
        )
        reimb.received_inflow = inflow
        reimb.received_amount = Decimal('6.00')
        reimb.save()
        
        self.assertEqual(reimb.pending_amount, Decimal('4.00'))
        
        # Financial summary should show Outflow=10, Inflow=6. Outflow is NOT reduced.
        self.assertEqual(get_total_actual_outflows(self.ngl, self.fy26), Decimal('10.00'))
        self.assertEqual(get_total_actual_inflows(self.ngl, self.fy26), Decimal('6.00'))

    def test_pass_through(self):
        OpeningBalance.objects.create(account=self.ngl, financial_year=self.fy26, balance_amount=Decimal('100.00'))
        
        Transaction.objects.create(
            account=self.ngl, financial_year=self.fy26, account_head=self.head_ngl,
            transaction_date=date(2026, 8, 1), direction=Transaction.Direction.OUTFLOW,
            amount=Decimal('30.00'), status=Transaction.Status.ACTIVE, pass_through=True
        )
        
        # Still reduces balance
        self.assertEqual(get_balance_available(self.ngl, self.fy26), Decimal('70.00'))
        self.assertEqual(get_pass_through_outflows(self.ngl, self.fy26), Decimal('30.00'))

    def test_transaction_number_generation(self):
        txn1 = Transaction.objects.create(
            account=self.ngl, financial_year=self.fy26, account_head=self.head_ngl,
            transaction_date=date(2026, 8, 1), direction=Transaction.Direction.INFLOW,
            amount=Decimal('10.00')
        )
        txn2 = Transaction.objects.create(
            account=self.ngl, financial_year=self.fy26, account_head=self.head_ngl,
            transaction_date=date(2026, 8, 2), direction=Transaction.Direction.INFLOW,
            amount=Decimal('20.00')
        )
        self.assertTrue(txn1.transaction_number.startswith('INST-01-NGL-TXN'))
        self.assertNotEqual(txn1.transaction_number, txn2.transaction_number)
        
    def test_invalid_fy_date(self):
        txn = Transaction(
            account=self.ngl, financial_year=self.fy26, account_head=self.head_ngl,
            transaction_date=date(2025, 8, 1), direction=Transaction.Direction.INFLOW,
            amount=Decimal('10.00')
        )
        with self.assertRaises(ValidationError):
            txn.full_clean()

    def test_invalid_account_head_link(self):
        txn = Transaction(
            account=self.ngl, financial_year=self.fy26, account_head=self.head_cpf,
            transaction_date=date(2026, 8, 1), direction=Transaction.Direction.INFLOW,
            amount=Decimal('10.00')
        )
        with self.assertRaises(ValidationError):
            txn.full_clean()
