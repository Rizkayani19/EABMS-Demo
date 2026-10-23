from datetime import date
import json

from django.contrib.auth.models import User
from django.http import Http404
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase
from django.views import View

from core.access_control import (
    force_active_account_filters,
    scoped_budget,
    scoped_reimbursement,
    transaction_view,
)
from core.bulk_transactions import TransactionBulkSaveView
from core.models import (
    Account,
    AccountHead,
    Budget,
    BudgetType,
    FinancialYear,
    Installation,
    Reimbursement,
    ReimbursementType,
    Transaction,
    UserProfile,
)
from core.views import FinancialEditMixin


class EditProbe(FinancialEditMixin, View):
    def get(self, request, *args, **kwargs):
        return 'ok'


class Gate112AccessControlTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.installation = Installation.objects.create(
            installation_code='TEST-11-2',
            installation_name='Gate 11.2 Test Installation',
        )
        self.account_a = Account.objects.create(
            installation=self.installation,
            code='A11',
            name='Account A 11.2',
        )
        self.account_b = Account.objects.create(
            installation=self.installation,
            code='B11',
            name='Account B 11.2',
        )
        self.fy_a = FinancialYear.objects.create(
            code='2030-31',
            name='FY 2030-31',
            start_date=date(2030, 7, 1),
            end_date=date(2031, 6, 30),
        )
        self.fy_b = FinancialYear.objects.create(
            code='2031-32',
            name='FY 2031-32',
            start_date=date(2031, 7, 1),
            end_date=date(2032, 6, 30),
        )
        self.head_a = AccountHead.objects.create(
            account=self.account_a,
            name='General A',
            head_type=AccountHead.HeadType.OUTFLOW,
        )
        self.budget_type = BudgetType.objects.create(code='INIT-11-2', name='Initial 11.2')
        self.outflow = Transaction.objects.create(
            account=self.account_a,
            financial_year=self.fy_a,
            account_head=self.head_a,
            transaction_date=date(2030, 8, 1),
            direction=Transaction.Direction.OUTFLOW,
            amount='100.00',
            status=Transaction.Status.ACTIVE,
        )
        self.budget_a = Budget.objects.create(
            account=self.account_a,
            financial_year=self.fy_a,
            status=Budget.Status.APPROVED,
        )
        self.user = User.objects.create_user(username='gate112-clerk', password='x')
        UserProfile.objects.create(user=self.user, role=UserProfile.Role.CLERK)
        self.management = User.objects.create_user(username='gate112-management', password='x')
        UserProfile.objects.create(user=self.management, role=UserProfile.Role.MANAGEMENT)

    def _request(self, account, fy, user=None):
        request = self.factory.get('/transactions/')
        request.account = account
        request.fy = fy
        request.user = user or self.user
        return request

    def test_transaction_route_rejects_cross_account_and_cross_fy(self):
        called = {'ok': False}

        def view(request, pk):
            called['ok'] = True
            return 'ok'

        wrapped = transaction_view(view)
        request = self._request(self.account_b, self.fy_a)
        with self.assertRaises(Http404):
            wrapped(request, pk=self.outflow.pk)
        self.assertFalse(called['ok'])

        request = self._request(self.account_a, self.fy_b)
        with self.assertRaises(Http404):
            wrapped(request, pk=self.outflow.pk)
        self.assertFalse(called['ok'])

    def test_budget_route_rejects_wrong_fy(self):
        called = {'ok': False}

        def view(request, pk):
            called['ok'] = True
            return 'ok'

        wrapped = scoped_budget(view)
        request = self._request(self.account_a, self.fy_b)
        with self.assertRaises(Http404):
            wrapped(request, pk=self.budget_a.pk)
        self.assertFalse(called['ok'])

    def test_reimbursement_route_rejects_wrong_account_and_fy(self):
        rb_type = ReimbursementType.objects.create(code='RB-11-2', name='Reimbursement 11.2')
        reimbursement = Reimbursement.objects.create(
            reimbursement_type=rb_type,
            original_outflow=self.outflow,
            expected_amount='50.00',
            source='Test source',
            expected_date=date(2030, 9, 1),
        )

        called = {'ok': False}

        def view(request, pk):
            called['ok'] = True
            return 'ok'

        wrapped = scoped_reimbursement(view)
        request = self._request(self.account_b, self.fy_a)
        with self.assertRaises(Http404):
            wrapped(request, pk=reimbursement.pk)
        request = self._request(self.account_a, self.fy_b)
        with self.assertRaises(Http404):
            wrapped(request, pk=reimbursement.pk)
        self.assertFalse(called['ok'])

    def test_list_policy_overrides_tampered_account_and_fy(self):
        request = self.factory.get('/transactions/?account=999&financial_year=999')
        request.account = self.account_a
        request.fy = self.fy_a
        request.user = self.user

        captured = {}

        def view(inner_request):
            captured['account'] = inner_request.GET['account']
            captured['fy'] = inner_request.GET['financial_year']
            return 'ok'

        wrapped = force_active_account_filters(view)
        self.assertEqual(wrapped(request), 'ok')
        self.assertEqual(captured['account'], str(self.account_a.pk))
        self.assertEqual(captured['fy'], str(self.fy_a.pk))

    def test_management_cannot_write_bulk_transactions(self):
        request = self.factory.post('/transactions/bulk-save/', data=json.dumps({'rows': []}), content_type='application/json')
        request.user = self.management
        response = TransactionBulkSaveView().post(request)
        self.assertEqual(response.status_code, 403)

    def test_management_is_denied_by_financial_edit_policy(self):
        request = self._request(self.account_a, self.fy_a, self.management)
        with self.assertRaises(PermissionDenied):
            EditProbe().dispatch(request)

    def test_clerk_is_allowed_through_financial_edit_policy(self):
        request = self._request(self.account_a, self.fy_a, self.user)
        self.assertEqual(EditProbe().dispatch(request), 'ok')
