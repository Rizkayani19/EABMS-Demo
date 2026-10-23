from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import Account, Installation, UserProfile


class Gate113NavigationShellTests(TestCase):
    def setUp(self):
        installation = Installation.objects.create(
            installation_code='NAV-11-3',
            installation_name='Navigation Test Installation',
        )
        account = Account.objects.create(
            installation=installation,
            code='NAV',
            name='Navigation Test Account',
        )
        user = User.objects.create_user(username='nav-user', password='StrongPass123!')
        UserProfile.objects.create(
            user=user,
            role=UserProfile.Role.CLERK,
            default_account=account,
        )
        self.client.force_login(user)

    def test_help_page_exposes_navigation_shell_contract(self):
        response = self.client.get(reverse('accounts:help'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="abms-sidebar"')
        self.assertContains(response, 'id="sidebar-collapse"')
        self.assertContains(response, 'id="sidebar-mobile-open"')
        self.assertContains(response, 'aria-label="Breadcrumb"')
        self.assertContains(response, 'Help & User Manual')
