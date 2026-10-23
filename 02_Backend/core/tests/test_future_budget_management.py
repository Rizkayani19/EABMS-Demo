from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from core.future_budget_management_models import FutureBudgetManagementInput
from core.future_budget_management_services import management_input_totals, save_management_input
from core.models import Account, AccountHead, FinancialYear, FutureBudget, Installation, InternalSection, Unit


class FutureBudgetManagementInputTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='budget-manager', password='test')
        self.installation = Installation.objects.create(installation_code='TEST-INST', installation_name='Test Installation')
        self.account = Account.objects.create(
            installation=self.installation, code='NGL-TEST', name='Test NGL'
        )
        self.source_fy = FinancialYear.objects.create(
            code='FY-TEST-S', name='FY 2025-26', start_date='2025-07-01', end_date='2026-06-30'
        )
        self.target_fy = FinancialYear.objects.create(
            code='FY-TEST-T', name='FY 2026-27', start_date='2026-07-01', end_date='2027-06-30'
        )
        self.future_budget = FutureBudget.objects.create(
            account=self.account, source_fy=self.source_fy, target_fy=self.target_fy
        )
        self.head = AccountHead.objects.create(
            account=self.account, code='H-01', name='Test Head', head_type='OUTFLOW'
        )
        self.unit = Unit.objects.create(code='TEST-UNIT', name='Test Unit')
        self.section = InternalSection.objects.create(code='TEST-SEC', name='Test Section')

    def test_management_input_supports_multi_unit_and_multi_section_attribution(self):
        second_unit = Unit.objects.create(code='TEST-UNIT-2', name='Test Unit 2')
        second_section = InternalSection.objects.create(code='TEST-SEC-2', name='Test Section 2')
        item = save_management_input(
            future_budget=self.future_budget,
            account_head=self.head,
            input_type=FutureBudgetManagementInput.InputType.ADDITIONAL,
            description='New capability requirement',
            amount=Decimal('1000000.00'),
            justification='Approved planning requirement for target FY.',
            user=self.user,
            units=[self.unit, second_unit],
            internal_sections=[self.section, second_section],
            status=FutureBudgetManagementInput.Status.ACTIVE,
        )
        self.assertEqual(item.units.count(), 2)
        self.assertEqual(item.internal_sections.count(), 2)
        self.assertEqual(item.amount, Decimal('1000000.00'))

    def test_totals_keep_continuing_and_additional_separate(self):
        save_management_input(
            future_budget=self.future_budget,
            account_head=self.head,
            input_type=FutureBudgetManagementInput.InputType.CONTINUING,
            description='Continuing requirement',
            amount=Decimal('250000.00'),
            justification='Required to continue the service.',
            status=FutureBudgetManagementInput.Status.ACTIVE,
        )
        save_management_input(
            future_budget=self.future_budget,
            account_head=self.head,
            input_type=FutureBudgetManagementInput.InputType.ADDITIONAL,
            description='Additional requirement',
            amount=Decimal('750000.00'),
            justification='New requirement for target FY.',
            status=FutureBudgetManagementInput.Status.ACTIVE,
        )
        totals = management_input_totals(self.future_budget, self.head)
        self.assertEqual(totals[FutureBudgetManagementInput.InputType.CONTINUING], Decimal('250000.00'))
        self.assertEqual(totals[FutureBudgetManagementInput.InputType.ADDITIONAL], Decimal('750000.00'))

    def test_draft_input_is_not_counted_in_active_totals(self):
        save_management_input(
            future_budget=self.future_budget,
            account_head=self.head,
            input_type=FutureBudgetManagementInput.InputType.CONTINUING,
            description='Draft requirement',
            amount=Decimal('900000.00'),
            justification='Still under review.',
            status=FutureBudgetManagementInput.Status.DRAFT,
        )
        totals = management_input_totals(self.future_budget, self.head)
        self.assertEqual(totals[FutureBudgetManagementInput.InputType.CONTINUING], Decimal('0.00'))

    def test_bulk_copy_suggested_to_proposed(self):
        from django.test import Client
        from django.urls import reverse
        from core.models import FutureBudgetLine, UserProfile

        UserProfile.objects.create(user=self.user, role=UserProfile.Role.MANAGEMENT)
        line = FutureBudgetLine.objects.create(
            future_budget=self.future_budget,
            account_head=self.head,
            system_suggested=Decimal('123456.00'),
            user_proposed=None,
        )

        client = Client()
        client.force_login(self.user)
        session = client.session
        session['active_account_id'] = self.account.id
        session['active_fy_id'] = self.source_fy.id
        session.save()

        response = client.post(
            reverse('core:future_budget_copy_suggested', kwargs={'pk': self.future_budget.pk}),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        line.refresh_from_db()
        self.assertEqual(line.user_proposed, Decimal('123456.00'))

    def test_bulk_save_all_proposals(self):
        from django.test import Client
        from django.urls import reverse
        from core.models import FutureBudgetLine, UserProfile

        UserProfile.objects.create(user=self.user, role=UserProfile.Role.MANAGEMENT)
        line1 = FutureBudgetLine.objects.create(
            future_budget=self.future_budget,
            account_head=self.head,
            system_suggested=Decimal('100000.00'),
            user_proposed=None,
        )
        head2 = AccountHead.objects.create(account=self.account, code='H-02', name='Head Two', head_type='OUTFLOW')
        line2 = FutureBudgetLine.objects.create(
            future_budget=self.future_budget,
            account_head=head2,
            system_suggested=Decimal('200000.00'),
            user_proposed=None,
        )

        client = Client()
        client.force_login(self.user)
        session = client.session
        session['active_account_id'] = self.account.id
        session['active_fy_id'] = self.source_fy.id
        session.save()

        post_data = {
            'line_ids': [str(line1.pk), str(line2.pk)],
            f'proposed_{line1.pk}': '150000.00',
            f'justification_{line1.pk}': 'Adjusted for inflation',
            f'proposed_{line2.pk}': '250000.00',
            f'justification_{line2.pk}': 'Additional requirements approved',
        }

        response = client.post(
            reverse('core:future_budget_save_all_proposals', kwargs={'pk': self.future_budget.pk}),
            post_data,
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        line1.refresh_from_db()
        line2.refresh_from_db()
        self.assertEqual(line1.user_proposed, Decimal('150000.00'))
        self.assertEqual(line1.justification, 'Adjusted for inflation')
        self.assertEqual(line2.user_proposed, Decimal('250000.00'))
        self.assertEqual(line2.justification, 'Additional requirements approved')

