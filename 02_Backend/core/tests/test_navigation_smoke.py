from uuid import uuid4

from django.test import SimpleTestCase
from django.urls import NoReverseMatch, reverse


class CanonicalNavigationSmokeTests(SimpleTestCase):
    def _assert_resolves(self, name, *args, **kwargs):
        try:
            url = reverse(name, args=args, kwargs=kwargs)
        except NoReverseMatch as exc:
            self.fail(f'Canonical route {name} does not resolve: {exc}')
        self.assertTrue(url.startswith('/'))

    def test_core_operational_routes_resolve(self):
        names = [
            'core:home',
            'core:transaction_list',
            'core:inflow_create',
            'core:outflow_create',
            'core:transaction_bulk_edit',
            'core:transaction_bulk_save',
            'core:transaction_bulk_delete',
            'core:reimbursement_list',
            'core:reimbursement_create',
            'core:data_administration',
            'core:import_create',
            'core:budget_list',
            'core:budget_create',
            'core:document_upload',
            'core:future_budget_list',
            'core:future_budget_create',
            'core:future_budget_planning',
        ]
        for name in names:
            with self.subTest(name=name):
                self._assert_resolves(name)

    def test_parameterized_core_operational_routes_resolve(self):
        tx_pk = uuid4()
        cases = [
            ('core:transaction_detail', {'pk': tx_pk}),
            ('core:transaction_edit', {'pk': tx_pk}),
            ('core:transaction_cancel', {'pk': tx_pk}),
            ('core:reimbursement_edit', {'pk': tx_pk}),
            ('core:transaction_restore', {'pk': tx_pk}),
            ('core:import_review', {'pk': 1}),
            ('core:budget_detail', {'pk': 1}),
            ('core:budget_edit', {'pk': 1}),
            ('core:budgetline_create', {'budget_id': 1}),
            ('core:budgetrevision_create', {'line_id': 1}),
            ('core:document_download', {'pk': 1}),
            ('core:future_budget_detail', {'pk': 1}),
            ('core:future_budget_review', {'pk': 1}),
            ('core:future_budget_review_build', {'pk': 1}),
            ('core:future_budget_management_input_create', {'pk': 1}),
            ('core:future_budget_line_edit', {'pk': 1}),
            ('core:future_budget_line_proposal', {'pk': 1}),
            ('core:future_budget_line_proposal_clear', {'pk': 1}),
            ('core:future_budget_allocation', {'pk': 1}),
            ('core:known_change_create', {'budget_id': 1}),
            ('core:personnel_plan', {'pk': 1}),
            ('core:propose_future_budget', {'pk': 1}),
            ('core:approve_future_budget', {'pk': 1}),
        ]
        for name, kwargs in cases:
            with self.subTest(name=name):
                self._assert_resolves(name, **kwargs)

    def test_accounts_masters_and_reports_namespaces_resolve(self):
        names = [
            'accounts:help',
            'accounts:audit_log',
            'masters:account_head_list',
            'masters:opening_balance_list',
            'masters:inflow_type_list',
            'masters:outflow_nature_list',
            'masters:budget_type_list',
            'masters:fy_list',
            'reports:report_center',
        ]
        for name in names:
            with self.subTest(name=name):
                self._assert_resolves(name)
