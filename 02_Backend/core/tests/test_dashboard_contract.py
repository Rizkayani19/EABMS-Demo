from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, SimpleTestCase

from core.views import home


class DashboardContractTests(SimpleTestCase):
    def test_home_uses_full_operational_dashboard(self):
        user = get_user_model()(username='dashboard-test')
        request = RequestFactory().get('/')
        request.user = user
        request.account = object()
        request.fy = object()

        dashboard = {
            'opening_balance': Decimal('100.00'),
            'total_inflows': Decimal('200.00'),
            'total_outflows': Decimal('50.00'),
            'balance_available': Decimal('250.00'),
            'approved_budget': Decimal('300.00'),
            'budget_consumed': Decimal('50.00'),
            'balance_of_budget': Decimal('250.00'),
            'budget_utilisation': Decimal('16.67'),
            'this_month_inflows': Decimal('20.00'),
            'this_month_outflows': Decimal('5.00'),
            'since_start_inflows': Decimal('200.00'),
            'since_start_outflows': Decimal('50.00'),
            'monthly_trend': [],
            'routine_outflows': Decimal('0.00'),
            'addl_outflows': Decimal('0.00'),
            'cont_outflows': Decimal('0.00'),
            'new_outflows': Decimal('0.00'),
            'pt_count': 0,
            'pt_outflows': Decimal('0.00'),
            'pending_reimb_count': 0,
            'pending_reimb_total': Decimal('0.00'),
            'reimbursement_summary': {},
            'top_budget_heads': [],
            'alerts': [],
        }

        with patch('core.views.get_dashboard_data', return_value=dashboard), patch('core.views.render') as render:
            response = home.__wrapped__(request)

        render.assert_called_once()
        self.assertEqual(render.call_args.args[1], 'core/index.html')
        context = render.call_args.args[2]
        self.assertEqual(context['total_inflows'], Decimal('200.00'))
        self.assertEqual(context['total_outflows'], Decimal('50.00'))
        self.assertIn('monthly_trend', context)
        self.assertIn('pending_reimb_count', context)
        self.assertIn('top_budget_heads', context)
        self.assertFalse(context['all_accounts_view'])
