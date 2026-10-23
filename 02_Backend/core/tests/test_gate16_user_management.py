from django.contrib.auth.models import User
from django.test import TestCase

from core.models import Account, Installation, UserProfile, AuditLog


class Gate16UserManagementTests(TestCase):
    def setUp(self):
        self.installation = Installation.objects.create(
            installation_code='G16-TEST',
            installation_name='Gate 16 Test Installation',
        )
        self.account = Account.objects.create(
            installation=self.installation,
            code='G16',
            name='Gate 16 Account',
            is_active=True,
        )
        self.admin = User.objects.create_user(username='g16-admin', password='AdminPass123!')
        UserProfile.objects.create(
            user=self.admin,
            role=UserProfile.Role.ADMINISTRATOR,
            default_account=self.account,
            is_active=True,
        )
        self.target = User.objects.create_user(
            username='g16-clerk',
            password='ClerkPass123!',
            first_name='Gate',
            last_name='Clerk',
            email='clerk@example.local',
        )
        UserProfile.objects.create(
            user=self.target,
            role=UserProfile.Role.CLERK,
            default_account=self.account,
            is_active=True,
        )
        self.client.force_login(self.admin)

    def test_admin_can_view_user_list(self):
        response = self.client.get('/accounts/users/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'g16-clerk')
        self.assertContains(response, 'Edit')
        self.assertContains(response, 'Reset Password')

    def test_admin_can_create_active_user(self):
        response = self.client.post(
            '/accounts/users/new/',
            {
                'username': 'g16-new-user',
                'first_name': 'New',
                'last_name': 'User',
                'email': 'new@example.local',
                'role': UserProfile.Role.CLERK,
                'default_account': str(self.account.pk),
                'is_active': 'on',
                'password1': 'StrongPass123!',
                'password2': 'StrongPass123!',
            },
        )
        self.assertRedirects(response, '/accounts/users/')
        user = User.objects.get(username='g16-new-user')
        self.assertTrue(user.is_active)
        self.assertEqual(user.profile.role, UserProfile.Role.CLERK)
        self.assertTrue(user.check_password('StrongPass123!'))
        self.assertTrue(AuditLog.objects.filter(action='CREATE_USER', record_id=str(user.pk)).exists())

    def test_admin_can_create_inactive_user(self):
        response = self.client.post(
            '/accounts/users/new/',
            {
                'username': 'g16-inactive',
                'first_name': 'Inactive',
                'last_name': 'User',
                'email': 'inactive@example.local',
                'role': UserProfile.Role.MANAGEMENT,
                'default_account': str(self.account.pk),
                'password1': 'StrongPass123!',
                'password2': 'StrongPass123!',
            },
        )
        self.assertRedirects(response, '/accounts/users/')
        user = User.objects.get(username='g16-inactive')
        self.assertFalse(user.is_active)
        self.assertFalse(user.profile.is_active)
        self.assertEqual(user.profile.role, UserProfile.Role.MANAGEMENT)

    def test_admin_can_update_user(self):
        response = self.client.post(
            f'/accounts/users/{self.target.pk}/edit/',
            {
                'username': self.target.username,
                'first_name': 'Updated',
                'last_name': 'User',
                'email': 'updated@example.local',
                'role': UserProfile.Role.MANAGEMENT,
                'default_account': str(self.account.pk),
                'is_active': 'on',
            },
        )
        self.assertRedirects(response, '/accounts/users/')
        self.target.refresh_from_db()
        self.target.profile.refresh_from_db()
        self.assertEqual(self.target.first_name, 'Updated')
        self.assertEqual(self.target.profile.role, UserProfile.Role.MANAGEMENT)
        self.assertTrue(AuditLog.objects.filter(action='UPDATE_USER', record_id=str(self.target.pk)).exists())

    def test_admin_can_reset_password(self):
        response = self.client.post(
            f'/accounts/users/{self.target.pk}/password/',
            {
                'new_password1': 'NewStrongPass123!',
                'new_password2': 'NewStrongPass123!',
            },
        )
        self.assertRedirects(response, '/accounts/users/')
        self.assertTrue(User.objects.get(pk=self.target.pk).check_password('NewStrongPass123!'))
        self.assertTrue(AuditLog.objects.filter(action='RESET_USER_PASSWORD', record_id=str(self.target.pk)).exists())

    def test_admin_can_deactivate_and_reactivate_user(self):
        response = self.client.post(f'/accounts/users/{self.target.pk}/toggle-active/')
        self.assertRedirects(response, '/accounts/users/')
        self.target.refresh_from_db()
        self.target.profile.refresh_from_db()
        self.assertFalse(self.target.is_active)
        self.assertFalse(self.target.profile.is_active)

        self.client.post(f'/accounts/users/{self.target.pk}/toggle-active/')
        self.target.refresh_from_db()
        self.target.profile.refresh_from_db()
        self.assertTrue(self.target.is_active)
        self.assertTrue(self.target.profile.is_active)

        self.assertTrue(AuditLog.objects.filter(action='DEACTIVATE_USER', record_id=str(self.target.pk)).exists())
        self.assertTrue(AuditLog.objects.filter(action='ACTIVATE_USER', record_id=str(self.target.pk)).exists())

    def test_admin_can_delete_user(self):
        target_id = self.target.pk
        response = self.client.post(f'/accounts/users/{target_id}/delete/')
        self.assertRedirects(response, '/accounts/users/')
        self.assertFalse(User.objects.filter(pk=target_id).exists())
        self.assertTrue(AuditLog.objects.filter(action='DELETE_USER', record_id=str(target_id)).exists())

    def test_admin_cannot_delete_self(self):
        response = self.client.post(f'/accounts/users/{self.admin.pk}/delete/')
        self.assertRedirects(response, '/accounts/users/')
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())

    def test_admin_cannot_deactivate_self(self):
        response = self.client.post(f'/accounts/users/{self.admin.pk}/toggle-active/')
        self.assertRedirects(response, '/accounts/users/')
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_last_active_administrator_is_protected(self):
        self.target.profile.role = UserProfile.Role.ADMINISTRATOR
        self.target.profile.save(update_fields=['role'])
        response = self.client.post(f'/accounts/users/{self.target.pk}/toggle-active/')
        self.assertRedirects(response, '/accounts/users/')
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)
        self.assertTrue(self.target.profile.is_active)

        response = self.client.post(
            f'/accounts/users/{self.target.pk}/edit/',
            {
                'username': self.target.username,
                'first_name': self.target.first_name,
                'last_name': self.target.last_name,
                'email': self.target.email,
                'role': UserProfile.Role.CLERK,
                'default_account': str(self.account.pk),
                'is_active': 'on',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'At least one active Administrator must remain in the system.')

    def test_non_admin_cannot_use_crud(self):
        self.client.force_login(self.target)
        self.assertEqual(self.client.get('/accounts/users/').status_code, 403)
        self.assertEqual(self.client.get(f'/accounts/users/{self.admin.pk}/edit/').status_code, 403)
