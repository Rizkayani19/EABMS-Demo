from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import Account, AuditLog, UserProfile, Installation


class Gate112UserManagementTests(TestCase):
    def setUp(self):
        installation = Installation.objects.create(
            installation_code='USER-11-2',
            installation_name='User Management Test Installation',
        )
        self.account = Account.objects.create(
            installation=installation,
            code='USR11',
            name='User Test Account',
        )
        self.admin = User.objects.create_user(username='admin-11-2', password='StrongPass123!')
        UserProfile.objects.create(
            user=self.admin,
            role=UserProfile.Role.ADMINISTRATOR,
            default_account=self.account,
        )
        self.clerk = User.objects.create_user(username='clerk-11-2', password='StrongPass123!')
        UserProfile.objects.create(
            user=self.clerk,
            role=UserProfile.Role.CLERK,
            default_account=self.account,
        )

    def test_help_is_available_to_authenticated_users(self):
        self.client.force_login(self.clerk)
        response = self.client.get(reverse('accounts:help'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Help & User Manual')

    def test_user_management_is_denied_to_non_administrator(self):
        self.client.force_login(self.clerk)
        response = self.client.get(reverse('accounts:user_create'))
        self.assertEqual(response.status_code, 403)

    def test_administrator_can_create_user_and_audit_is_written(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('accounts:user_create'), data={
            'username': 'new-clerk',
            'first_name': 'New',
            'last_name': 'Clerk',
            'email': 'new-clerk@example.local',
            'role': UserProfile.Role.CLERK,
            'default_account': self.account.pk,
            'is_active': 'on',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        })
        self.assertRedirects(response, reverse('accounts:user_list'))
        user = User.objects.get(username='new-clerk')
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.profile.role, UserProfile.Role.CLERK)
        self.assertEqual(user.profile.default_account_id, self.account.pk)
        self.assertTrue(AuditLog.objects.filter(action='CREATE_USER', record_id=str(user.pk)).exists())
