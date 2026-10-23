from functools import wraps

from django.http import Http404

from .models import (
    AccountHead,
    Budget,
    BudgetLine,
    Document,
    FutureBudget,
    FutureBudgetLine,
    Reimbursement,
    Transaction,
)


def _require_account(request):
    account = getattr(request, "account", None)
    if account is None:
        raise Http404("Active Account context is required.")
    return account


def _require_fy(request):
    return getattr(request, "fy", None)


def _fy_matches(request, fy_id):
    active_fy = _require_fy(request)
    return active_fy is None or str(fy_id) == str(active_fy.pk)


def force_active_account_filters(view_func):
    """Force list/filter requests to the current Account/FY context."""
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        account = _require_account(request)
        mutable = request.GET.copy()
        mutable["account"] = str(account.pk)
        fy = _require_fy(request)
        if fy is not None:
            mutable["financial_year"] = str(fy.pk)
        request.GET = mutable
        return view_func(request, *args, **kwargs)
    return wrapped


def account_scoped_object(view_func, object_loader):
    """Allow an object route only when the target object belongs to the active Account/FY scope."""
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        account = _require_account(request)
        obj = object_loader(request, kwargs)
        if obj is None:
            print("DEBUG: obj is None")
        elif getattr(obj, "account_id", None) != account.pk:
            print(f"DEBUG: obj.account_id {getattr(obj, 'account_id', None)} != account.pk {account.pk}")
        if obj is None or getattr(obj, "account_id", None) != account.pk:
            raise Http404("Record not found in the active Account.")
        if hasattr(obj, "financial_year_id"):
            # Historical transactions span across FYs, allow viewing them
            if not getattr(obj, "is_historical", False):
                if not _fy_matches(request, obj.financial_year_id):
                    raise Http404("Record not found in the active Financial Year.")
        return view_func(request, *args, **kwargs)
    return wrapped


def transaction_view(view_func):
    return account_scoped_object(
        view_func,
        lambda request, kwargs: Transaction.objects.filter(
            pk=kwargs.get("pk"), account=_require_account(request)
        ).first(),
    )


def scoped_reimbursement(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        account = _require_account(request)
        reimbursement = Reimbursement.objects.filter(
            pk=kwargs.get("pk"), original_outflow__account=account
        ).select_related("original_outflow__financial_year").first()
        if reimbursement is None:
            raise Http404("Reimbursement not found in the active Account.")
        if not _fy_matches(request, reimbursement.original_outflow.financial_year_id):
            raise Http404("Reimbursement not found in the active Financial Year.")
        return view_func(request, *args, **kwargs)
    return wrapped


def scoped_budget(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        account = _require_account(request)
        b_id = kwargs.get("pk") or kwargs.get("budget_id")
        budget = Budget.objects.filter(pk=b_id, account=account).first()
        if budget is None:
            raise Http404("Budget not found in the active Account.")
        if not _fy_matches(request, budget.financial_year_id):
            raise Http404("Budget not found in the active Financial Year.")
        return view_func(request, *args, **kwargs)
    return wrapped


def scoped_budget_line(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        account = _require_account(request)
        line = BudgetLine.objects.select_related("budget").filter(pk=kwargs.get("line_id")).first()
        if line is None or line.budget.account_id != account.pk:
            raise Http404("Budget Line not found in the active Account.")
        if not _fy_matches(request, line.budget.financial_year_id):
            raise Http404("Budget Line not found in the active Financial Year.")
        return view_func(request, *args, **kwargs)
    return wrapped


def scoped_future_budget(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        account = _require_account(request)
        b_id = kwargs.get("pk") or kwargs.get("budget_id")
        if not FutureBudget.objects.filter(pk=b_id, account=account).exists():
            raise Http404("Future Budget not found in the active Account.")
        return view_func(request, *args, **kwargs)
    return wrapped


def scoped_future_budget_line(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        account = _require_account(request)
        line = FutureBudgetLine.objects.select_related("future_budget").filter(pk=kwargs.get("pk")).first()
        if line is None or line.future_budget.account_id != account.pk:
            raise Http404("Future Budget Line not found in the active Account.")
        return view_func(request, *args, **kwargs)
    return wrapped


def scoped_account_head_ajax(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        account = _require_account(request)
        head_id = request.GET.get("account_head")
        if head_id and not AccountHead.objects.filter(pk=head_id, account=account).exists():
            raise Http404("Account Head not found in the active Account.")
        return view_func(request, *args, **kwargs)
    return wrapped


def scoped_document(view_func):
    """A document is accessible only when a link resolves to the active Account/FY context."""
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        account = _require_account(request)
        document = Document.objects.filter(pk=kwargs.get("pk"), active=True).first()
        if document is None:
            raise Http404("Document not found.")

        active_fy = _require_fy(request)
        for link in document.links.all():
            entity_id = link.entity_id
            allowed = False
            if link.entity_type == "TRANSACTION":
                tx = Transaction.objects.filter(pk=entity_id, account=account).first()
                allowed = tx is not None and _fy_matches(request, tx.financial_year_id)
            elif link.entity_type == "REIMBURSEMENT":
                rb = Reimbursement.objects.filter(pk=entity_id, original_outflow__account=account).select_related("original_outflow").first()
                allowed = rb is not None and _fy_matches(request, rb.original_outflow.financial_year_id)
            elif link.entity_type == "BUDGET":
                budget = Budget.objects.filter(pk=entity_id, account=account).first()
                allowed = budget is not None and _fy_matches(request, budget.financial_year_id)
            elif link.entity_type == "BUDGET_LINE":
                line = BudgetLine.objects.select_related("budget").filter(pk=entity_id, budget__account=account).first()
                allowed = line is not None and _fy_matches(request, line.budget.financial_year_id)
            elif link.entity_type == "FUTURE_BUDGET":
                allowed = FutureBudget.objects.filter(pk=entity_id, account=account).exists()
            elif link.entity_type == "FUTURE_BUDGET_LINE":
                allowed = FutureBudgetLine.objects.filter(pk=entity_id, future_budget__account=account).exists()

            if allowed:
                return view_func(request, *args, **kwargs)

        raise Http404("Document not found in the active Account/Financial Year.")
    return wrapped
