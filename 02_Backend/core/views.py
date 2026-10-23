from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from .dashboard_services import get_dashboard_data
from .models import Budget, Document, DocumentLink, FutureBudget, UserProfile


@login_required
def home(request):
    """Full operational ABMS dashboard for the active Account/FY."""
    from decimal import Decimal
    account = request.account
    fy = request.fy
    profile = getattr(request.user, 'profile', None)
    is_management = bool(profile and profile.role in [UserProfile.Role.MANAGEMENT, UserProfile.Role.ADMINISTRATOR]) or request.user.is_superuser

    all_accounts_param = request.GET.get('all_accounts') == '1'
    if all_accounts_param and is_management:
        from .models import Account
        accounts = Account.objects.filter(is_active=True).order_by('code')
        consolidated_data = []
        gt_budget = Decimal('0.00')
        gt_inflows = Decimal('0.00')
        gt_outflows = Decimal('0.00')
        gt_bal_avail = Decimal('0.00')

        for acc in accounts:
            data = get_dashboard_data(acc, fy) if fy else {}
            appr = data.get('approved_budget', Decimal('0.00'))
            inf = data.get('total_inflows', Decimal('0.00'))
            outf = data.get('total_outflows', Decimal('0.00'))
            bal = data.get('balance_available', Decimal('0.00'))

            gt_budget += appr
            gt_inflows += inf
            gt_outflows += outf
            gt_bal_avail += bal

            consolidated_data.append({
                'account': acc.code,
                'approved_budget': appr,
                'inflows': inf,
                'outflows': outf,
                'balance_available': bal,
                **data,
            })

        return render(request, 'core/index.html', {
            'account': account,
            'fy': fy,
            'is_management': is_management,
            'all_accounts_view': True,
            'consolidated_data': consolidated_data,
            'grand_totals': {
                'approved_budget': gt_budget,
                'inflows': gt_inflows,
                'outflows': gt_outflows,
                'balance_available': gt_bal_avail,
            },
        })

    dashboard = get_dashboard_data(account, fy) if account and fy else {}
    return render(request, 'core/index.html', {
        'account': account,
        'fy': fy,
        'is_management': is_management,
        'all_accounts_view': False,
        **dashboard,
    })


@login_required
def reconcile_opening_balance(request):
    """Compatibility entry point for the legacy dashboard quick action."""
    return redirect('masters:opening_balance_list')


class BaseFinanceView(LoginRequiredMixin, View):
    """Shared context for canonical budget views."""
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['account'] = self.request.account
        context['fy'] = self.request.fy
        return context


class FinancialEditMixin:
    """Block management-only users from editing budget records."""
    def dispatch(self, request, *args, **kwargs):
        profile = getattr(request.user, 'profile', None)
        if profile and profile.role == UserProfile.Role.MANAGEMENT:
            raise PermissionDenied('Management role cannot edit financial records.')
        return super().dispatch(request, *args, **kwargs)


class DocumentUploadView(FinancialEditMixin, BaseFinanceView, View):
    """Upload a standalone supporting document for the active financial year."""
    template_name = 'finance/document_upload.html'

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, {'account': request.account, 'fy': request.fy})

    def post(self, request, *args, **kwargs):
        upload = request.FILES.get('file') or request.FILES.get('document')
        if not upload:
            return render(request, self.template_name, {
                'account': request.account,
                'fy': request.fy,
                'error': 'Please select a document to upload.',
            })
        from .models import DocumentType
        document_type_id = request.POST.get('document_type')
        document_type = None
        if document_type_id:
            document_type = DocumentType.objects.filter(pk=document_type_id).first()
        if document_type is None:
            document_type = DocumentType.objects.filter(code='GENERAL', is_active=True).first()
        if document_type is None:
            document_type = DocumentType.objects.create(code='GENERAL', name='General Document')

        document = Document.objects.create(
            document_type=document_type,
            file=upload,
            file_name=upload.name,
            reference_no=request.POST.get('reference_no', ''),
            description=request.POST.get('description', ''),
            financial_year=request.fy,
            uploaded_by=request.user,
        )
        entity_type = request.POST.get('entity_type')
        entity_id = request.POST.get('entity_id')
        if entity_type and entity_id:
            DocumentLink.objects.create(
                document=document,
                entity_type=entity_type,
                entity_id=entity_id,
                created_by=request.user,
            )

        messages.success(request, 'Document uploaded successfully.')
        next_url = request.POST.get('next') or request.GET.get('next')
        if next_url:
            return redirect(next_url)
        return redirect('core:transaction_list')


class SecureDocumentDownloadView(LoginRequiredMixin, View):
    """Download an active document, scoped to the active financial year."""
    def get(self, request, pk, *args, **kwargs):
        document = get_object_or_404(Document, pk=pk, active=True)
        if document.financial_year_id and getattr(request, 'fy', None):
            if document.financial_year_id != request.fy.id:
                raise Http404
        try:
            response = FileResponse(document.file.open('rb'), as_attachment=True, filename=document.file_name)
        except (FileNotFoundError, OSError):
            raise Http404
        return response


def web_manifest(request):
    from django.http import JsonResponse
    from django.conf import settings
    fund_code = getattr(settings, 'ABMS_FUND', 'NGL')
    fund_names = {
        'NGL': 'NexGen Holdings Ltd.',
        'EWF': 'Employee Welfare Fund',
        'CPF': 'Corporate Provident Fund',
    }
    fund_name = fund_names.get(fund_code, 'Enterprise Accounts & Business Management System (EABMS)')
    theme_colors = {
        'NGL': '#0f172a',
        'EWF': '#881337',
        'CPF': '#064e3b',
    }
    theme_color = theme_colors.get(fund_code, '#0f172a')
    code_lower = fund_code.lower()

    manifest_data = {
        "name": f"{fund_name} - ABMS",
        "short_name": f"ABMS-{fund_code}",
        "description": f"{fund_name} Desktop Application",
        "start_url": f"/?account={fund_code}",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": theme_color,
        "icons": [
            {
                "src": f"/static/icons/{code_lower}.png",
                "sizes": "256x256",
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": f"/static/icons/{code_lower}.ico",
                "sizes": "64x64 32x32 24x24 16x16",
                "type": "image/x-icon"
            }
        ]
    }
    return JsonResponse(manifest_data, content_type='application/manifest+json')


@login_required
def trigger_backup(request):
    """Trigger an immediate manual database backup for the active fund."""
    import os
    from pathlib import Path
    from django.conf import settings
    from core.management.commands.backup_database import Command

    fund_code = getattr(settings, "ABMS_FUND", "") or os.environ.get("ABMS_FUND", "NGL").strip().upper()
    folder_name = f"backup_{fund_code}" if fund_code else "backups"
    backup_dir = Path(settings.BASE_DIR) / folder_name

    try:
        cmd = Command()
        snapshot = cmd.perform_backup(backup_dir, fund_code=fund_code)
        cmd.prune_old_backups(backup_dir, retention=1000)
        size_kb = snapshot.stat().st_size / 1024
        messages.success(
            request,
            f"Backup created successfully: {snapshot.name} ({size_kb:.1f} KB) in folder '{folder_name}/'."
        )
    except Exception as exc:
        messages.error(request, f"Manual backup failed: {exc}")

    next_url = request.META.get('HTTP_REFERER') or '/'
    return redirect(next_url)


