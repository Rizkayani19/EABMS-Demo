from django.conf import settings
from .models import Account, FinancialYear

def abms_context(request):
    """
    Supplies global template context:
    - Active Account (defaults to NexGen Holdings Ltd.)
    - Active Financial Year (defaults to 2026-27, status OPEN)
    - User Role (Admin / Clerk / Management)
    - List of available accounts and FYs for seamless switching
    """
    account = getattr(request, 'account', None)
    fy = getattr(request, 'fy', None)

    fund_code = getattr(settings, 'ABMS_FUND', 'NGL')
    fund_name = getattr(settings, 'ABMS_FUND_NAME', 'NexGen Holdings Ltd.')

    user_role = None
    if request.user.is_authenticated:
        if hasattr(request.user, 'profile'):
            user_role = request.user.profile.role
        elif request.user.is_superuser:
            user_role = 'ADMINISTRATOR'

    return {
        'current_account': account,
        'current_fy': fy,
        'active_fund_code': fund_code,
        'active_fund_name': fund_name,
        'fund_icon_path': f'icons/{fund_code.lower()}.ico',
        'fund_png_path': f'icons/{fund_code.lower()}.png',
        'available_accounts': Account.objects.filter(is_active=True).order_by('display_order', 'name'),
        'available_fys': FinancialYear.objects.filter(status=FinancialYear.Status.OPEN).order_by('-start_date'),
        'user_role': user_role,
        'system_name': getattr(settings, 'ABMS_SYSTEM_NAME', 'Enterprise Accounts & Business Management System (EABMS)'),
        'currency_symbol': getattr(settings, 'ABMS_CURRENCY_SYMBOL', '$'),
    }
