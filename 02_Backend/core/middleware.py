from .models import Account, FinancialYear
from .services import get_active_account, get_active_fy

class AccountContextMiddleware:
    """
    Ensures every request has a resolved `request.account` and `request.fy`.
    Defaults cleanly to NexGen Holdings Ltd. and FY 2026-27.
    Supports switching via query params: ?switch_account=, ?account=, ?switch_fy=, ?fy=
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Allow quick switching via query param or session
        acct_param = request.GET.get('switch_account') or request.GET.get('account')
        if acct_param:
            if acct_param.isdigit():
                request.session['active_account_id'] = int(acct_param)
            else:
                acc_obj = Account.objects.filter(code__iexact=acct_param.strip(), is_active=True).first()
                if acc_obj:
                    request.session['active_account_id'] = acc_obj.id

        fy_param = request.GET.get('switch_fy') or request.GET.get('fy')
        if fy_param:
            if fy_param.isdigit():
                request.session['active_fy_id'] = int(fy_param)
            else:
                fy_obj = FinancialYear.objects.filter(code__iexact=fy_param.strip()).first()
                if fy_obj:
                    request.session['active_fy_id'] = fy_obj.id

        request.account = get_active_account(request)
        request.fy = get_active_fy(request)

        response = self.get_response(request)
        return response

