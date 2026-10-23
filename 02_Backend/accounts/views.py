from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseRedirect
from core.models import Account, FinancialYear, AuditLog


def login_view(request):
    if request.user.is_authenticated:
        return redirect('core:home')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)

            if hasattr(user, 'profile') and user.profile.default_account:
                request.session['active_account_id'] = user.profile.default_account.id

            messages.success(request, f"Welcome back, {user.get_full_name() or user.username}!")
            next_url = request.GET.get('next') or 'core:home'
            return redirect(next_url)
        else:
            messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm()

    return render(request, 'auth/login.html', {'form': form})


def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out successfully.")
    return redirect('accounts:login')


@login_required
def switch_account(request, account_id):
    account = get_object_or_404(Account, pk=account_id, is_active=True)
    request.session['active_account_id'] = account.id
    messages.success(request, f"Active account switched to: {account.name}")
    redirect_url = request.META.get('HTTP_REFERER', '/')
    return HttpResponseRedirect(redirect_url)


@login_required
def switch_fy(request, fy_id):
    from core.models import FinancialYear
    fy = get_object_or_404(FinancialYear, pk=fy_id)
    request.session['active_fy_id'] = fy.id
    messages.success(request, f"Active financial year switched to: {fy.name}")
    redirect_url = request.META.get('HTTP_REFERER', '/')
    return HttpResponseRedirect(redirect_url)


@login_required
def audit_log_view(request):
    logs = AuditLog.objects.all().select_related('actor', 'account')[:200]
    return render(request, 'auth/audit_log.html', {'logs': logs})


from .views_gate112_additions import (
    help_manual,
    user_list,
    user_create,
    user_update,
    user_password_reset,
    user_toggle_active,
    user_delete,
    user_bulk_delete,
)
