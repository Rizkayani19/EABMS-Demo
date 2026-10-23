from functools import wraps

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from core.models import AuditLog, UserProfile
from .forms import AdminPasswordResetForm, AdminUserCreationForm, AdminUserUpdateForm


def administrator_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapped(request, *args, **kwargs):
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        profile = getattr(request.user, 'profile', None)
        if not profile or profile.role != UserProfile.Role.ADMINISTRATOR or not profile.is_active:
            raise PermissionDenied('Administrator role is required.')
        return view_func(request, *args, **kwargs)
    return wrapped


def _active_administrator_count():
    return User.objects.filter(
        is_active=True,
        profile__role=UserProfile.Role.ADMINISTRATOR,
        profile__is_active=True,
    ).count() + User.objects.filter(is_active=True, is_superuser=True).exclude(
        profile__role=UserProfile.Role.ADMINISTRATOR,
    ).count()


def _audit_user_change(actor, target, action, old_values=None, new_values=None):
    profile = getattr(target, 'profile', None)
    AuditLog.objects.create(
        actor=actor,
        account=getattr(profile, 'default_account', None),
        action=action,
        model_name='User',
        record_id=str(target.pk),
        record_repr=target.username,
        old_values=old_values,
        new_values=new_values,
    )


def _user_snapshot(user):
    profile = getattr(user, 'profile', None)
    return {
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'email': user.email,
        'role': getattr(profile, 'role', None),
        'default_account_id': getattr(profile, 'default_account_id', None),
        'is_active': bool(user.is_active and getattr(profile, 'is_active', False)),
        'is_staff': user.is_staff,
        'is_superuser': user.is_superuser,
    }


@login_required
def help_manual(request):
    return render(request, 'help/index.html')


@administrator_required
def user_list(request):
    users = User.objects.select_related('profile', 'profile__default_account').order_by('username')
    return render(request, 'accounts/user_list.html', {'users': users})


@administrator_required
def user_create(request):
    if request.method == 'POST':
        form = AdminUserCreationForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = form.save(commit=True)
                profile, _ = UserProfile.objects.get_or_create(user=user)
                profile.role = form.cleaned_data['role']
                profile.default_account = form.cleaned_data['default_account']
                profile.is_active = form.cleaned_data['is_active']
                profile.save()
                _audit_user_change(
                    request.user,
                    user,
                    'CREATE_USER',
                    new_values=_user_snapshot(user),
                )
            messages.success(request, f'User {user.username} created successfully.')
            return redirect('accounts:user_list')
    else:
        form = AdminUserCreationForm()
    return render(request, 'accounts/user_form.html', {'form': form, 'title': 'New User', 'mode': 'create'})


@administrator_required
def user_update(request, user_id):
    target = get_object_or_404(User.objects.select_related('profile'), pk=user_id)
    if request.method == 'POST':
        form = AdminUserUpdateForm(request.POST, instance=target)
        if form.is_valid():
            old = _user_snapshot(target)
            requested_active = form.cleaned_data['is_active']
            requested_role = form.cleaned_data['role']
            if target.pk == request.user.pk and not requested_active:
                form.add_error('is_active', 'You cannot deactivate your own Administrator account.')
            elif (
                old['role'] == UserProfile.Role.ADMINISTRATOR
                and old['is_active']
                and (requested_role != UserProfile.Role.ADMINISTRATOR or not requested_active)
                and _active_administrator_count() <= 2
            ):
                form.add_error(None, 'At least one active Administrator must remain in the system.')
            else:
                with transaction.atomic():
                    user = form.save(commit=True)
                    profile, _ = UserProfile.objects.get_or_create(user=user)
                    profile.role = requested_role
                    profile.default_account = form.cleaned_data['default_account']
                    profile.is_active = requested_active
                    user.is_active = requested_active
                    user.save(update_fields=['is_active'])
                    profile.save()
                    new = _user_snapshot(user)
                    _audit_user_change(request.user, user, 'UPDATE_USER', old_values=old, new_values=new)
                    if user.pk == request.user.pk:
                        update_session_auth_hash(request, user)
                messages.success(request, f'User {target.username} updated successfully.')
                return redirect('accounts:user_list')
    else:
        form = AdminUserUpdateForm(instance=target)
    return render(request, 'accounts/user_form.html', {
        'form': form,
        'title': f'Edit User — {target.username}',
        'mode': 'edit',
        'target_user': target,
    })


@administrator_required
def user_password_reset(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    if request.method == 'POST':
        form = AdminPasswordResetForm(target, request.POST)
        if form.is_valid():
            form.save()
            _audit_user_change(request.user, target, 'RESET_USER_PASSWORD', new_values={'username': target.username})
            messages.success(request, f'Password reset for {target.username}.')
            return redirect('accounts:user_list')
    else:
        form = AdminPasswordResetForm(target)
    return render(request, 'accounts/user_password_reset.html', {'form': form, 'target_user': target})


@administrator_required
def user_toggle_active(request, user_id):
    target = get_object_or_404(User.objects.select_related('profile'), pk=user_id)
    if request.method != 'POST':
        return redirect('accounts:user_list')

    profile, _ = UserProfile.objects.get_or_create(user=target)
    currently_active = bool(target.is_active and profile.is_active)
    if target.pk == request.user.pk and currently_active:
        messages.error(request, 'You cannot deactivate your own Administrator account.')
        return redirect('accounts:user_list')
    if currently_active and profile.role == UserProfile.Role.ADMINISTRATOR and _active_administrator_count() <= 2:
        messages.error(request, 'At least one active Administrator must remain in the system.')
        return redirect('accounts:user_list')

    old = _user_snapshot(target)
    target.is_active = not currently_active
    profile.is_active = not currently_active
    with transaction.atomic():
        target.save(update_fields=['is_active'])
        profile.save(update_fields=['is_active'])
        _audit_user_change(
            request.user,
            target,
            'DEACTIVATE_USER' if currently_active else 'ACTIVATE_USER',
            old_values=old,
            new_values=_user_snapshot(target),
        )
    messages.success(request, f'User {target.username} is now {"Inactive" if currently_active else "Active"}.')
    return redirect('accounts:user_list')


@administrator_required
def user_delete(request, user_id):
    target = get_object_or_404(User.objects.select_related('profile'), pk=user_id)
    if request.method != 'POST':
        return redirect('accounts:user_list')
    if target.pk == request.user.pk:
        messages.error(request, 'You cannot delete your own Administrator account.')
        return redirect('accounts:user_list')
    profile = getattr(target, 'profile', None)
    if target.is_active and profile and profile.role == UserProfile.Role.ADMINISTRATOR and profile.is_active and _active_administrator_count() <= 2:
        messages.error(request, 'The last active Administrator cannot be deleted.')
        return redirect('accounts:user_list')

    old = _user_snapshot(target)
    username = target.username
    with transaction.atomic():
        _audit_user_change(request.user, target, 'DELETE_USER', old_values=old)
        target.delete()
    messages.success(request, f'User {username} deleted permanently.')
    return redirect('accounts:user_list')


@administrator_required
def user_bulk_delete(request):
    if request.method != 'POST':
        return redirect('accounts:user_list')

    import json
    ids = request.POST.getlist('selected_ids') or request.POST.getlist('ids')
    if not ids:
        raw = request.POST.get('selected_ids') or request.POST.get('ids') or ''
        if raw.startswith('[') and raw.endswith(']'):
            try:
                ids = json.loads(raw)
            except Exception:
                ids = []
        elif raw:
            ids = [i.strip() for i in raw.split(',') if i.strip()]

    if not ids:
        messages.warning(request, 'No users were selected for deletion.')
        return redirect('accounts:user_list')

    deleted_count = 0
    protected_self = 0
    protected_last_admin = 0

    for user_id in ids:
        try:
            target = User.objects.select_related('profile').get(pk=user_id)
        except User.DoesNotExist:
            continue

        if target.pk == request.user.pk:
            protected_self += 1
            continue

        profile = getattr(target, 'profile', None)
        if target.is_active and profile and profile.role == UserProfile.Role.ADMINISTRATOR and profile.is_active and _active_administrator_count() <= 2:
            protected_last_admin += 1
            continue

        old = _user_snapshot(target)
        with transaction.atomic():
            _audit_user_change(request.user, target, 'DELETE_USER', old_values=old)
            target.delete()
            deleted_count += 1

    if deleted_count > 0:
        messages.success(request, f'Successfully deleted {deleted_count} user(s).')
    if protected_self > 0:
        messages.warning(request, 'Your own logged-in account cannot be deleted.')
    if protected_last_admin > 0:
        messages.warning(request, 'The active Administrator cannot be deleted to ensure system management continuity.')

    return redirect('accounts:user_list')
