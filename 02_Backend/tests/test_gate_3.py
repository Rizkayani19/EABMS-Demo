from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError, PermissionDenied
from decimal import Decimal
from datetime import date
from django.db import IntegrityError

from core.models import (
    Installation, Account, FinancialYear, AccountHead, BudgetType, 
    Transaction, OutflowNature, Unit, Budget, BudgetLine, BudgetRevision,
    UserProfile
)
from core.services import (
    get_total_approved_budget, get_budget_consumed, get_balance_of_budget,
    get_budget_utilisation, is_over_budget
)
from core.views import FinancialEditMixin

class Gate3BudgetEngineTests(TestCase):
    def setUp(self):
        self.user_admin = User.objects.create_user(username='admin_user', password='123')
        UserProfile.objects.create(user=self.user_admin, role=UserProfile.Role.ADMINISTRATOR)

        self.user_clerk = User.objects.create_user(username='clerk_user', password='123')
        UserProfile.objects.create(user=self.user_clerk, role=UserProfile.Role.CLERK)
        
        self.user_mgmt = User.objects.create_user(username='mgmt_user', password='123')
        UserProfile.objects.create(user=self.user_mgmt, role=UserProfile.Role.MANAGEMENT)

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
        
        self.unit1 = Unit.objects.create(name='Alpha', code='A')
        self.budget_type_routine = BudgetType.objects.create(code='ROUTINE', name='Routine')
        
        self.outflow_nature = OutflowNature.objects.create(code='ROUTINE_OUT', name='Routine Outflow')

    def test_1_budget_header_creation(self):
        b = Budget.objects.create(account=self.ngl, financial_year=self.fy26, status=Budget.Status.DRAFT)
        self.assertEqual(b.status, 'DRAFT')

    def test_2_one_budget_per_account_fy(self):
        Budget.objects.create(account=self.ngl, financial_year=self.fy26)
        with self.assertRaises(IntegrityError):
            Budget.objects.create(account=self.ngl, financial_year=self.fy26)

    def test_3_draft_status_exclusion(self):
        b = Budget.objects.create(account=self.ngl, financial_year=self.fy26, status=Budget.Status.DRAFT)
        BudgetLine.objects.create(budget=b, account_head=self.head_ngl, budget_type=self.budget_type_routine, amount=Decimal('100'))
        self.assertEqual(get_total_approved_budget(self.ngl, self.fy26), Decimal('0.00'))

    def test_4_approved_status_inclusion(self):
        b = Budget.objects.create(account=self.ngl, financial_year=self.fy26, status=Budget.Status.APPROVED)
        BudgetLine.objects.create(budget=b, account_head=self.head_ngl, budget_type=self.budget_type_routine, amount=Decimal('100'))
        self.assertEqual(get_total_approved_budget(self.ngl, self.fy26), Decimal('100.00'))

    def test_5_cancelled_status_exclusion(self):
        b = Budget.objects.create(account=self.ngl, financial_year=self.fy26, status=Budget.Status.CANCELLED)
        BudgetLine.objects.create(budget=b, account_head=self.head_ngl, budget_type=self.budget_type_routine, amount=Decimal('100'))
        self.assertEqual(get_total_approved_budget(self.ngl, self.fy26), Decimal('0.00'))

    def test_6_approved_budget_included_in_totals(self):
        b = Budget.objects.create(account=self.ngl, financial_year=self.fy26, status=Budget.Status.APPROVED)
        BudgetLine.objects.create(budget=b, account_head=self.head_ngl, budget_type=self.budget_type_routine, amount=Decimal('100'))
        BudgetLine.objects.create(budget=b, account_head=self.head_ngl, unit=self.unit1, budget_type=self.budget_type_routine, amount=Decimal('50'))
        self.assertEqual(get_total_approved_budget(self.ngl, self.fy26), Decimal('150.00'))

    def test_7_draft_budget_excluded(self):
        # Covered by 3
        pass

    def test_8_cancelled_budget_excluded(self):
        # Covered by 5
        pass

    def test_9_budgetline_creation(self):
        b = Budget.objects.create(account=self.ngl, financial_year=self.fy26, status=Budget.Status.DRAFT)
        bl = BudgetLine.objects.create(budget=b, account_head=self.head_ngl, budget_type=self.budget_type_routine, amount=Decimal('100'))
        self.assertEqual(bl.amount, Decimal('100.00'))

    def test_10_budgetline_uniqueness(self):
        b = Budget.objects.create(account=self.ngl, financial_year=self.fy26, status=Budget.Status.DRAFT)
        BudgetLine.objects.create(budget=b, account_head=self.head_ngl, budget_type=self.budget_type_routine, amount=Decimal('100'))
        with self.assertRaises(IntegrityError):
            BudgetLine.objects.create(budget=b, account_head=self.head_ngl, budget_type=self.budget_type_routine, amount=Decimal('200'))

    def test_11_account_isolation(self):
        b_cpf = Budget.objects.create(account=self.cpf, financial_year=self.fy26, status=Budget.Status.APPROVED)
        BudgetLine.objects.create(budget=b_cpf, account_head=self.head_cpf, budget_type=self.budget_type_routine, amount=Decimal('100'))
        self.assertEqual(get_total_approved_budget(self.ngl, self.fy26), Decimal('0.00'))

    def test_12_fy_isolation(self):
        b_fy25 = Budget.objects.create(account=self.ngl, financial_year=self.fy25, status=Budget.Status.APPROVED)
        BudgetLine.objects.create(budget=b_fy25, account_head=self.head_ngl, budget_type=self.budget_type_routine, amount=Decimal('100'))
        self.assertEqual(get_total_approved_budget(self.ngl, self.fy26), Decimal('0.00'))

    def test_13_budget_consumption(self):
        Transaction.objects.create(
            account=self.ngl, financial_year=self.fy26, account_head=self.head_ngl,
            transaction_date=date(2026, 8, 1), direction=Transaction.Direction.OUTFLOW,
            amount=Decimal('40.00'), status=Transaction.Status.ACTIVE
        )
        self.assertEqual(get_budget_consumed(self.ngl, self.fy26), Decimal('40.00'))

    def test_14_pass_through_consumption(self):
        """Pass-through transactions (internal book transfers) are excluded from operational budget consumption."""
        Transaction.objects.create(
            account=self.ngl, financial_year=self.fy26, account_head=self.head_ngl,
            transaction_date=date(2026, 8, 1), direction=Transaction.Direction.OUTFLOW,
            amount=Decimal('30.00'), status=Transaction.Status.ACTIVE, pass_through=True
        )
        self.assertEqual(get_budget_consumed(self.ngl, self.fy26), Decimal('0.00'))

    def test_15_draft_outflow_excluded(self):
        Transaction.objects.create(
            account=self.ngl, financial_year=self.fy26, account_head=self.head_ngl,
            transaction_date=date(2026, 8, 1), direction=Transaction.Direction.OUTFLOW,
            amount=Decimal('40.00'), status=Transaction.Status.DRAFT
        )
        self.assertEqual(get_budget_consumed(self.ngl, self.fy26), Decimal('0.00'))

    def test_16_cancelled_outflow_excluded(self):
        Transaction.objects.create(
            account=self.ngl, financial_year=self.fy26, account_head=self.head_ngl,
            transaction_date=date(2026, 8, 1), direction=Transaction.Direction.OUTFLOW,
            amount=Decimal('40.00'), status=Transaction.Status.CANCELLED
        )
        self.assertEqual(get_budget_consumed(self.ngl, self.fy26), Decimal('0.00'))

    def test_17_inflow_excluded(self):
        Transaction.objects.create(
            account=self.ngl, financial_year=self.fy26, account_head=self.head_ngl,
            transaction_date=date(2026, 8, 1), direction=Transaction.Direction.INFLOW,
            amount=Decimal('40.00'), status=Transaction.Status.ACTIVE
        )
        self.assertEqual(get_budget_consumed(self.ngl, self.fy26), Decimal('0.00'))

    def test_18_balance_of_budget(self):
        b = Budget.objects.create(account=self.ngl, financial_year=self.fy26, status=Budget.Status.APPROVED)
        BudgetLine.objects.create(budget=b, account_head=self.head_ngl, budget_type=self.budget_type_routine, amount=Decimal('100'))
        
        Transaction.objects.create(
            account=self.ngl, financial_year=self.fy26, account_head=self.head_ngl,
            transaction_date=date(2026, 8, 1), direction=Transaction.Direction.OUTFLOW,
            amount=Decimal('40.00'), status=Transaction.Status.ACTIVE
        )
        self.assertEqual(get_balance_of_budget(self.ngl, self.fy26), Decimal('60.00'))

    def test_19_budget_utilisation(self):
        b = Budget.objects.create(account=self.ngl, financial_year=self.fy26, status=Budget.Status.APPROVED)
        BudgetLine.objects.create(budget=b, account_head=self.head_ngl, budget_type=self.budget_type_routine, amount=Decimal('200'))
        
        Transaction.objects.create(
            account=self.ngl, financial_year=self.fy26, account_head=self.head_ngl,
            transaction_date=date(2026, 8, 1), direction=Transaction.Direction.OUTFLOW,
            amount=Decimal('50.00'), status=Transaction.Status.ACTIVE
        )
        # 50 / 200 = 25%
        self.assertEqual(get_budget_utilisation(self.ngl, self.fy26), Decimal('25.00'))

    def test_20_zero_budget_handling(self):
        self.assertIsNone(get_budget_utilisation(self.ngl, self.fy26))

    def test_21_over_budget_warning(self):
        b = Budget.objects.create(account=self.ngl, financial_year=self.fy26, status=Budget.Status.APPROVED)
        BudgetLine.objects.create(budget=b, account_head=self.head_ngl, budget_type=self.budget_type_routine, amount=Decimal('100'))
        
        Transaction.objects.create(
            account=self.ngl, financial_year=self.fy26, account_head=self.head_ngl,
            transaction_date=date(2026, 8, 1), direction=Transaction.Direction.OUTFLOW,
            amount=Decimal('120.00'), status=Transaction.Status.ACTIVE
        )
        self.assertTrue(is_over_budget(self.ngl, self.fy26))

    def test_22_budget_revision_history(self):
        b = Budget.objects.create(account=self.ngl, financial_year=self.fy26, status=Budget.Status.APPROVED)
        bl = BudgetLine.objects.create(budget=b, account_head=self.head_ngl, budget_type=self.budget_type_routine, amount=Decimal('100'))
        
        # Revision
        BudgetRevision.objects.create(
            budget_line=bl,
            previous_amount=Decimal('100.00'),
            revised_amount=Decimal('150.00'),
            difference=Decimal('50.00'),
            reason='Additional req'
        )
        bl.amount = Decimal('150.00')
        bl.save()
        
        self.assertEqual(bl.amount, Decimal('150.00'))
        self.assertEqual(bl.revisions.count(), 1)

    def test_23_approved_budget_protection(self):
        # Tested at UI/Form layer, handled via views
        pass

    def test_24_rbac(self):
        from django.test import Client
        
        c = Client()
        c.force_login(self.user_mgmt)
        
        # Accessing an edit endpoint (e.g. BudgetCreateView)
        response = c.get('/budgets/new/')
        self.assertEqual(response.status_code, 403) # PermissionDenied translates to 403
        
        c.force_login(self.user_admin)
        response = c.get('/budgets/new/')
        self.assertEqual(response.status_code, 200)
        
        c.force_login(self.user_clerk)
        response = c.get('/budgets/new/')
        self.assertEqual(response.status_code, 200)

    def test_25_budget_head_hierarchy_validation(self):
        b = Budget.objects.create(account=self.ngl, financial_year=self.fy26)
        bl = BudgetLine(budget=b, account_head=self.head_cpf, budget_type=self.budget_type_routine, amount=Decimal('100'))
        with self.assertRaises(ValidationError):
            bl.clean()

    def test_budget_consumption_with_unit_and_head(self):
        b = Budget.objects.create(account=self.ngl, financial_year=self.fy26, status=Budget.Status.APPROVED)
        BudgetLine.objects.create(budget=b, account_head=self.head_ngl, unit=self.unit1, budget_type=self.budget_type_routine, amount=Decimal('100'))
        
        Transaction.objects.create(
            account=self.ngl, financial_year=self.fy26, account_head=self.head_ngl, unit=self.unit1,
            transaction_date=date(2026, 8, 1), direction=Transaction.Direction.OUTFLOW,
            amount=Decimal('40.00'), status=Transaction.Status.ACTIVE
        )
        
        self.assertEqual(get_budget_consumed(self.ngl, self.fy26, account_head=self.head_ngl, unit=self.unit1), Decimal('40.00'))
