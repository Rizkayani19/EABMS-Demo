from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.db.models import ProtectedError
from django.urls import reverse
from core.models import (
    Installation, Account, FinancialYear, AccountHead,
    OpeningBalance, UserProfile, Unit, OutflowNature
)
from decimal import Decimal
from datetime import date


class InstallationAndAccountArchitectureTests(TestCase):
    """
    Tests for Gate 1.5 Tasks 1, 2, 3, 7, 8:
    1. Installation exists.
    2. Accounts belong to correct installation.
    3. Strict account isolation.
    4. NGL seed integrity (24 heads).
    5. CPF / EWF do not inherit NGL heads.
    6. Protected deletion of referenced masters.
    7. Account context middleware resolution.
    """

    def setUp(self):
        # Create installation
        self.inst = Installation.objects.create(
            installation_code='INST-01',
            installation_name='Main Installation'
        )

        # Create 3 official accounts
        self.ngl = Account.objects.create(
            installation=self.inst,
            code='NGL',
            name='NexGen Holdings',
            display_order=1
        )
        self.cpf = Account.objects.create(
            installation=self.inst,
            code='CPF',
            name='Corporate Provident Fund',
            display_order=2
        )
        self.ewf = Account.objects.create(
            installation=self.inst,
            code='EWF',
            name='Corporate Haj and Umra Fund',
            display_order=3
        )

        # Create FY 2026-27
        self.fy = FinancialYear.objects.create(
            code='2026-27',
            name='FY 2026-27',
            start_date=date(2026, 7, 1),
            end_date=date(2027, 6, 30),
            status=FinancialYear.Status.OPEN
        )

        # Create 24 NGL heads
        self.ngl_head_names = [
            "B.B.F", "Sty", "IT", "Fin Asst Indls", "Capacity Enhancement / Northern Branch",
            "Fin Asst Security Unit", "Fin Asst Units", "Late Sitting", "Lunch Staff",
            "Contract Salaries", "Standing Sanc", "Utility / Maint", "Loan",
            "Rent Charges", "Office Misc Exp", "Monthly profit on running acct",
            "Received from HQO", "Received from Group", "Amount Tfr from EVT",
            "Amount Tfr from TRV", "Corporate Staff Hand Book", "Received from ACAD Atd",
            "Received from BR-EAST Cen", "Bank Guarantee Off"
        ]

        for idx, name in enumerate(self.ngl_head_names, start=1):
            AccountHead.objects.create(
                account=self.ngl,
                code=f"NGL-{idx:02d}",
                name=name,
                display_order=idx
            )

        # Create users
        self.admin_user = User.objects.create_superuser('admin_test', 'admin@test.local', 'pass123')
        UserProfile.objects.create(user=self.admin_user, role=UserProfile.Role.ADMINISTRATOR, default_account=self.ngl)

        self.clerk_user = User.objects.create_user('clerk_test', 'clerk@test.local', 'pass123')
        UserProfile.objects.create(user=self.clerk_user, role=UserProfile.Role.CLERK, default_account=self.ngl)

        self.client = Client()

    def test_01_installation_exists(self):
        """Test 1: Installation exists and holds required attributes."""
        self.assertIsNotNone(self.inst.id)
        self.assertEqual(self.inst.installation_code, 'INST-01')
        self.assertTrue(self.inst.is_active)

    def test_02_accounts_belong_to_installation(self):
        """Test 2: All 3 accounts are properly linked to the installation."""
        accounts = Account.objects.filter(installation=self.inst)
        self.assertEqual(accounts.count(), 3)
        self.assertEqual(set(accounts.values_list('code', flat=True)), {'NGL', 'CPF', 'EWF'})

    def test_03_account_isolation(self):
        """Test 3: Operational records are strictly isolated by account FK."""
        # Create a head on CPF
        cpf_head = AccountHead.objects.create(
            account=self.cpf,
            code='CPF-01',
            name='Ceremony Uniforms'
        )

        ngl_heads = AccountHead.objects.filter(account=self.ngl)
        cpf_heads = AccountHead.objects.filter(account=self.cpf)

        self.assertNotIn(cpf_head, ngl_heads)
        self.assertIn(cpf_head, cpf_heads)
        self.assertEqual(cpf_heads.count(), 1)

    def test_04_ngl_seed_integrity(self):
        """Test 4: Exactly 24 Account Heads exist for NGL."""
        ngl_count = AccountHead.objects.filter(account=self.ngl).count()
        self.assertEqual(ngl_count, 24)

    def test_05_cpf_and_ewf_have_zero_ngl_heads(self):
        """Test 5: CPF and EWF do not inherit any of NGL's 24 heads."""
        cpf_count = AccountHead.objects.filter(account=self.cpf).count()
        ewf_count = AccountHead.objects.filter(account=self.ewf).count()
        self.assertEqual(cpf_count, 0)
        self.assertEqual(ewf_count, 0)

    def test_06_protected_deletion_of_referenced_masters(self):
        """Test 9: Account with dependent AccountHeads cannot be destructively deleted."""
        with self.assertRaises(ProtectedError):
            self.ngl.delete()

    def test_07_account_context_middleware_default(self):
        """Test 12: Account Context Middleware defaults to NGL."""
        self.client.login(username='clerk_test', password='pass123')
        response = self.client.get(reverse('core:home'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['current_account'].code, 'NGL')
        self.assertEqual(response.context['current_fy'].code, '2026-27')

    def test_08_account_context_switching(self):
        """Test 12: Switching account via session updates active context."""
        self.client.login(username='admin_test', password='pass123')
        switch_url = reverse('accounts:switch_account', args=[self.cpf.id])
        response = self.client.get(switch_url, HTTP_REFERER=reverse('core:home'), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['current_account'].code, 'CPF')
