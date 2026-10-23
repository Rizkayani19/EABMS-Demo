from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, ProtectedError
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from core.models import (
    Installation, Account, FinancialYear, Unit, MajorHead, SubHead,
    InflowType, OutflowNature, BudgetType, ReimbursementType, DocumentType,
    PersonnelClassification, AccountHead, OpeningBalance
)
from core.services import log_audit_action
from masters.models import City, CeremonyVenue, CeremonyEvent, Cohort, CohortPackage, Pilgrim, TourOperator
from .forms import (
    CityForm, CeremonyVenueForm, CeremonyEventForm, CohortForm,
    CohortPackageForm, PilgrimForm, TourOperatorForm,
    InstallationForm, AccountForm, FinancialYearForm, UnitForm,
    MajorHeadForm, SubHeadForm, InflowTypeForm, OutflowNatureForm,
    BudgetTypeForm, ReimbursementTypeForm, DocumentTypeForm,
    PersonnelClassificationForm, AccountHeadForm, OpeningBalanceForm
)

@login_required
def account_head_list(request):
    account = request.account
    q = request.GET.get('q', '').strip()
    head_type = request.GET.get('head_type', '').strip()
    status = request.GET.get('status', 'all').strip()
    selected_account_id = request.GET.get('account_id')

    if selected_account_id and selected_account_id.isdigit():
        target_account = Account.objects.filter(pk=int(selected_account_id)).first()
        if target_account:
            account = target_account

    queryset = AccountHead.objects.all().select_related('account', 'major_head', 'sub_head')
    if account:
        queryset = queryset.filter(account=account)
    if q:
        queryset = queryset.filter(Q(name__icontains=q) | Q(code__icontains=q) | Q(description__icontains=q))
    if head_type in [AccountHead.HeadType.OUTFLOW, AccountHead.HeadType.INFLOW, AccountHead.HeadType.BOTH]:
        queryset = queryset.filter(head_type=head_type)
    if status == 'active':
        queryset = queryset.filter(is_active=True)
    elif status == 'inactive':
        queryset = queryset.filter(is_active=False)

    major_head_id = request.GET.get('major_head_id', '').strip()
    if major_head_id and major_head_id.isdigit():
        queryset = queryset.filter(major_head_id=int(major_head_id))

    queryset = queryset.order_by('major_head__display_order', 'display_order', 'name')
    available_major_heads = MajorHead.objects.filter(account=account).order_by('display_order', 'name') if account else MajorHead.objects.filter(is_active=True).order_by('display_order', 'name')
    context = {
        'account_heads': queryset, 'selected_account': account, 'q': q,
        'head_type': head_type, 'status': status, 'major_head_id': major_head_id,
        'available_major_heads': available_major_heads, 'total_count': queryset.count(),
    }
    if request.headers.get('HX-Request') and not request.GET.get('full_page'):
        return render(request, 'masters/partials/account_head_table.html', context)
    return render(request, 'masters/account_head_list.html', context)


@login_required
def account_head_create(request):
    if request.method == 'POST':
        form = AccountHeadForm(request.POST, account=request.account)
        if form.is_valid():
            head = form.save()
            log_audit_action(actor=request.user, action='CREATE', instance=head,
                             new_values={'name': head.name, 'code': head.code, 'head_type': head.head_type, 'account': head.account.name},
                             account=head.account)
            messages.success(request, f"Account Head '{head.name}' created successfully for {head.account.name}.")
            return redirect('masters:account_head_list')
    else:
        form = AccountHeadForm(account=request.account, initial={'account': request.account})
    return render(request, 'masters/account_head_form.html', {'form': form, 'title': 'New Account Head', 'is_edit': False})


@login_required
def account_head_update(request, pk):
    head = get_object_or_404(AccountHead, pk=pk)
    old_data = {'name': head.name, 'code': head.code, 'head_type': head.head_type, 'is_active': head.is_active}
    if request.method == 'POST':
        form = AccountHeadForm(request.POST, instance=head, account=head.account)
        if form.is_valid():
            head = form.save()
            new_data = {'name': head.name, 'code': head.code, 'head_type': head.head_type, 'is_active': head.is_active}
            log_audit_action(actor=request.user, action='UPDATE', instance=head, old_values=old_data, new_values=new_data, account=head.account)
            messages.success(request, f"Account Head '{head.name}' updated successfully.")
            return redirect('masters:account_head_list')
    else:
        form = AccountHeadForm(instance=head, account=head.account)
    return render(request, 'masters/account_head_form.html', {'form': form, 'head': head, 'title': f'Edit Account Head: {head.name}', 'is_edit': True})


@login_required
def account_head_toggle_active(request, pk):
    head = get_object_or_404(AccountHead, pk=pk)
    old_status = head.is_active
    head.is_active = not head.is_active
    head.save()
    action = 'ACTIVATE' if head.is_active else 'DEACTIVATE'
    log_audit_action(actor=request.user, action=action, instance=head, old_values={'is_active': old_status}, new_values={'is_active': head.is_active}, account=head.account)
    if request.headers.get('HX-Request'):
        return render(request, 'masters/partials/account_head_row.html', {'head': head})
    messages.info(request, f"Account Head '{head.name}' {'activated' if head.is_active else 'deactivated'}.")
    return redirect('masters:account_head_list')


def _extract_ids(request):
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
    return [i for i in ids if i]


@login_required
def account_head_bulk_delete(request):
    ids = _extract_ids(request)
    if not ids:
        messages.warning(request, "No account heads selected for deletion.")
        return redirect('masters:account_head_list')

    deleted_count = 0
    protected_items = []

    for head_id in ids:
        try:
            head = AccountHead.objects.get(pk=head_id)
            log_audit_action(actor=request.user, action='DELETE', instance=head, account=head.account)
            head.delete()
            deleted_count += 1
        except ProtectedError:
            protected_items.append(str(head))
        except AccountHead.DoesNotExist:
            continue

    if deleted_count > 0:
        messages.success(request, f"Successfully deleted {deleted_count} Account Head(s).")
    if protected_items:
        names_preview = ", ".join(protected_items[:3])
        if len(protected_items) > 3:
            names_preview += f" and {len(protected_items) - 3} more"
        messages.warning(request, f"{len(protected_items)} Account Head(s) could not be deleted because they are referenced in transactions or budgets ({names_preview}).")
    return redirect('masters:account_head_list')

@login_required  
def sub_head_options_for_account(request):
    """Return SubHead options HTML for a given account_id (HTMX)."""
    account_id = request.GET.get('account_id') or request.GET.get('account') or (request.account.id if hasattr(request, 'account') else None)
    from core.models import SubHead
    sub_heads = SubHead.objects.filter(account_id=account_id).order_by('name') if account_id else SubHead.objects.none()
    html = '<option value="">---------</option>'
    html += ''.join(f'<option value="{s.pk}">{s.name}</option>' for s in sub_heads)
    return HttpResponse(html)


# ==============================================================================
# GENERIC MASTER CRUD VIEW FACTORY
# ==============================================================================

def create_master_views(model_class, form_class, model_name, url_namespace, has_status_field=False):
    """Generate standard CRUD list/form/toggle/bulk-delete views for core master tables."""
    @login_required
    def list_view(request):
        q = request.GET.get('q', '').strip()
        status = request.GET.get('status', 'all').strip()
        queryset = model_class.objects.all()

        # Isolate by active account if model supports account direct or through cohort
        if hasattr(model_class, 'account') and hasattr(request, 'account') and request.account:
            queryset = queryset.filter(account=request.account)
        elif hasattr(model_class, 'cohort') and hasattr(request, 'account') and request.account:
            queryset = queryset.filter(cohort__account=request.account)

        if q:
            if hasattr(model_class, 'code') and hasattr(model_class, 'name'):
                queryset = queryset.filter(Q(name__icontains=q) | Q(code__icontains=q))
            elif hasattr(model_class, 'package_code') and hasattr(model_class, 'package_name'):
                queryset = queryset.filter(Q(package_name__icontains=q) | Q(package_code__icontains=q))
            elif hasattr(model_class, 'installation_code'):
                queryset = queryset.filter(Q(installation_name__icontains=q) | Q(installation_code__icontains=q))
            elif hasattr(model_class, 'name'):
                queryset = queryset.filter(name__icontains=q)
            elif hasattr(model_class, 'employee_no') and hasattr(model_class, 'name_and_designation'):
                queryset = queryset.filter(Q(employee_no__icontains=q) | Q(name_and_designation__icontains=q))

        if has_status_field:
            if status in ['OPEN', 'CLOSED', 'ARCHIVED']:
                queryset = queryset.filter(status=status)
        elif hasattr(model_class, 'is_active'):
            if status == 'active': queryset = queryset.filter(is_active=True)
            elif status == 'inactive': queryset = queryset.filter(is_active=False)
        if hasattr(model_class, 'display_order'):
            queryset = queryset.order_by('display_order')
        context = {'items': queryset, 'model_name': model_name, 'url_namespace': url_namespace, 'q': q,
                   'status': status, 'has_status_field': has_status_field, 'total_count': queryset.count()}
        return render(request, 'masters/master_list.html', context)

    def _filter_form_fields_for_account(form, account):
        """Restrict form dropdown choices strictly to the active account."""
        if not account or not hasattr(form, 'fields'):
            return
        if 'account' in form.fields:
            form.fields['account'].initial = account
            form.fields['account'].queryset = Account.objects.filter(pk=account.pk)
        if 'cohort' in form.fields:
            form.fields['cohort'].queryset = Cohort.objects.filter(account=account, is_active=True)
        if 'major_head' in form.fields:
            form.fields['major_head'].queryset = MajorHead.objects.filter(account=account, is_active=True)
        if 'sub_head' in form.fields:
            form.fields['sub_head'].queryset = SubHead.objects.filter(account=account, is_active=True)
        if 'venue' in form.fields:
            form.fields['venue'].queryset = CeremonyVenue.objects.filter(is_active=True)

    @login_required
    def create_view(request):
        if request.method == 'POST':
            form = form_class(request.POST)
            _filter_form_fields_for_account(form, request.account)
            if form.is_valid():
                item = form.save(commit=False)
                if hasattr(item, 'account') and hasattr(request, 'account') and request.account and not item.account_id:
                    item.account = request.account
                item.save()
                log_audit_action(actor=request.user, action='CREATE', instance=item,
                                 account=getattr(item, 'account', getattr(request, 'account', None)))
                messages.success(request, f"{model_name} '{item}' created successfully.")
                return redirect(f'masters:{url_namespace}_list')
        else:
            initial = {}
            if hasattr(model_class, 'account') and hasattr(request, 'account') and request.account:
                initial['account'] = request.account
            form = form_class(initial=initial)
            _filter_form_fields_for_account(form, request.account)
        template_name = 'masters/package_form.html' if url_namespace == 'package' else 'masters/master_form.html'
        return render(request, template_name, {'form': form, 'model_name': model_name, 'title': f'New {model_name}', 'url_namespace': url_namespace, 'is_edit': False})

    @login_required
    def update_view(request, pk):
        item = get_object_or_404(model_class, pk=pk)
        item_account = getattr(item, 'account', getattr(request, 'account', None))
        if request.method == 'POST':
            form = form_class(request.POST, instance=item)
            _filter_form_fields_for_account(form, item_account)
            if form.is_valid():
                item = form.save()
                log_audit_action(actor=request.user, action='UPDATE', instance=item,
                                 account=getattr(item, 'account', getattr(request, 'account', None)))
                messages.success(request, f"{model_name} '{item}' updated successfully.")
                return redirect(f'masters:{url_namespace}_list')
        else:
            form = form_class(instance=item)
            _filter_form_fields_for_account(form, item_account)
        template_name = 'masters/package_form.html' if url_namespace == 'package' else 'masters/master_form.html'
        return render(request, template_name, {'form': form, 'item': item, 'model_name': model_name, 'title': f'Edit {model_name}: {item}', 'url_namespace': url_namespace, 'is_edit': True})

    @login_required
    def toggle_view(request, pk):
        item = get_object_or_404(model_class, pk=pk)
        if hasattr(item, 'status'):
            if item.status == FinancialYear.Status.OPEN:
                item.status = FinancialYear.Status.CLOSED
            elif item.status == FinancialYear.Status.CLOSED:
                item.status = FinancialYear.Status.ARCHIVED
            else:
                item.status = FinancialYear.Status.OPEN
            item.save()
            log_audit_action(actor=request.user, action='STATUS_CHANGE', instance=item)
            messages.info(request, f"{model_name} '{item.name}' status set to {item.get_status_display()}.")
        elif hasattr(item, 'is_active'):
            item.is_active = not item.is_active
            item.save()
            action = 'ACTIVATE' if item.is_active else 'DEACTIVATE'
            log_audit_action(actor=request.user, action=action, instance=item)
            messages.info(request, f"{model_name} '{item}' {'activated' if item.is_active else 'deactivated'}.")
        return redirect(f'masters:{url_namespace}_list')

    @login_required
    def bulk_delete_view(request):
        ids = _extract_ids(request)
        if not ids:
            messages.warning(request, f"No {model_name.lower()} records selected for deletion.")
            return redirect(f'masters:{url_namespace}_list')

        deleted_count = 0
        protected_items = []

        for item_id in ids:
            try:
                item = model_class.objects.get(pk=item_id)
                log_audit_action(actor=request.user, action='DELETE', instance=item)
                item.delete()
                deleted_count += 1
            except ProtectedError:
                protected_items.append(str(item))
            except model_class.DoesNotExist:
                continue

        if deleted_count > 0:
            messages.success(request, f"Successfully deleted {deleted_count} {model_name}(s).")
        if protected_items:
            names_preview = ", ".join(protected_items[:3])
            if len(protected_items) > 3:
                names_preview += f" and {len(protected_items) - 3} more"
            messages.warning(request, f"{len(protected_items)} {model_name}(s) could not be deleted because they are referenced in active transactions ({names_preview}).")
        return redirect(f'masters:{url_namespace}_list')

    return list_view, create_view, update_view, toggle_view, bulk_delete_view


installation_list, installation_create, installation_update, installation_toggle, installation_bulk_delete = create_master_views(Installation, InstallationForm, 'Installation', 'installation')
account_list, account_create, account_update, account_toggle, account_bulk_delete = create_master_views(Account, AccountForm, 'Account', 'account')
fy_list, fy_create, fy_update, fy_toggle, fy_bulk_delete = create_master_views(FinancialYear, FinancialYearForm, 'Financial Year', 'fy', has_status_field=True)
unit_list, unit_create, unit_update, unit_toggle, unit_bulk_delete = create_master_views(Unit, UnitForm, 'Unit', 'unit')
major_head_list, major_head_create, major_head_update, major_head_toggle, major_head_bulk_delete = create_master_views(MajorHead, MajorHeadForm, 'Sub Fund', 'major_head')
sub_head_list, sub_head_create, sub_head_update, sub_head_toggle, sub_head_bulk_delete = create_master_views(SubHead, SubHeadForm, 'Sub Head', 'sub_head')
inflow_type_list, inflow_type_create, inflow_type_update, inflow_type_toggle, inflow_type_bulk_delete = create_master_views(InflowType, InflowTypeForm, 'Inflow Type', 'inflow_type')
outflow_nature_list, outflow_nature_create, outflow_nature_update, outflow_nature_toggle, outflow_nature_bulk_delete = create_master_views(OutflowNature, OutflowNatureForm, 'Outflow Nature', 'outflow_nature')
budget_type_list, budget_type_create, budget_type_update, budget_type_toggle, budget_type_bulk_delete = create_master_views(BudgetType, BudgetTypeForm, 'Budget Type', 'budget_type')
reimbursement_type_list, reimbursement_type_create, reimbursement_type_update, reimbursement_type_toggle, reimbursement_type_bulk_delete = create_master_views(ReimbursementType, ReimbursementTypeForm, 'Reimbursement Type', 'reimbursement_type')
document_type_list, document_type_create, document_type_update, document_type_toggle, document_type_bulk_delete = create_master_views(DocumentType, DocumentTypeForm, 'Document Type', 'document_type')
personnel_classification_list, personnel_classification_create, personnel_classification_update, personnel_classification_toggle, personnel_classification_bulk_delete = create_master_views(PersonnelClassification, PersonnelClassificationForm, 'Personnel Classification', 'personnel_classification')
city_list, city_create, city_update, city_toggle, city_bulk_delete = create_master_views(City, CityForm, 'City', 'city')
ceremony_venue_list, ceremony_venue_create, ceremony_venue_update, ceremony_venue_toggle, ceremony_venue_bulk_delete = create_master_views(CeremonyVenue, CeremonyVenueForm, 'Ceremony Venue', 'ceremony_venue')
ceremony_event_list, ceremony_event_create, ceremony_event_update, ceremony_event_toggle, ceremony_event_bulk_delete = create_master_views(CeremonyEvent, CeremonyEventForm, 'Ceremony Event', 'ceremony_event')
cohort_list, cohort_create, cohort_update, cohort_toggle, cohort_bulk_delete = create_master_views(Cohort, CohortForm, 'Cohort', 'cohort')
_, _, _, package_toggle, package_bulk_delete = create_master_views(CohortPackage, CohortPackageForm, 'Cohort Package', 'package')


@login_required
def package_list(request):
    """Rich, conspicuous listing for Haj & Umra Cohort Packages with dedicated filter tabs."""
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', 'all').strip()
    package_type = request.GET.get('package_type', '').strip().upper()
    cohort_id = request.GET.get('cohort_id', '').strip()

    base_qs = CohortPackage.objects.all().select_related('cohort', 'cohort__account')
    if hasattr(request, 'account') and request.account:
        base_qs = base_qs.filter(cohort__account=request.account)

    total_count = base_qs.count()
    umra_count = base_qs.filter(package_type=CohortPackage.PackageType.UMRA).count()
    haj_count = base_qs.filter(package_type=CohortPackage.PackageType.HAJ).count()

    queryset = base_qs
    if q:
        queryset = queryset.filter(
            Q(package_name__icontains=q) |
            Q(package_code__icontains=q) |
            Q(cohort__code__icontains=q) |
            Q(cohort__title__icontains=q) |
            Q(medina_hotel_name__icontains=q) |
            Q(makkah_p1_hotel_name__icontains=q) |
            Q(airline__icontains=q)
        )

    if status == 'active':
        queryset = queryset.filter(is_active=True)
    elif status == 'inactive':
        queryset = queryset.filter(is_active=False)

    if cohort_id and cohort_id.isdigit():
        queryset = queryset.filter(cohort_id=int(cohort_id))

    if package_type in [CohortPackage.PackageType.UMRA, CohortPackage.PackageType.HAJ]:
        queryset = queryset.filter(package_type=package_type)

    queryset = queryset.order_by('-package_type', 'cohort__code', 'package_name')

    cohorts = Cohort.objects.filter(is_active=True)
    if hasattr(request, 'account') and request.account:
        cohorts = cohorts.filter(account=request.account)

    context = {
        'items': queryset,
        'model_name': 'Cohort Package',
        'url_namespace': 'package',
        'q': q,
        'status': status,
        'package_type': package_type,
        'cohort_id': cohort_id,
        'cohorts': cohorts,
        'total_count': total_count,
        'umra_count': umra_count,
        'haj_count': haj_count,
    }
    return render(request, 'masters/package_list.html', context)


@login_required
def package_create(request):
    """Create a new Haj or Umra cohort package, with optional copy-from-existing support."""
    copy_from_id = request.GET.get('copy_from')
    if copy_from_id and copy_from_id.isdigit():
        return redirect('masters:package_copy', pk=int(copy_from_id))

    available_packages = CohortPackage.objects.filter(is_active=True).select_related('cohort')
    if hasattr(request, 'account') and request.account:
        available_packages = available_packages.filter(cohort__account=request.account)

    if request.method == 'POST':
        form = CohortPackageForm(request.POST)
        if hasattr(request, 'account') and request.account and 'cohort' in form.fields:
            form.fields['cohort'].queryset = Cohort.objects.filter(account=request.account, is_active=True)
        if form.is_valid():
            item = form.save()
            log_audit_action(
                actor=request.user, action='CREATE', instance=item,
                account=getattr(item.cohort, 'account', getattr(request, 'account', None))
            )
            messages.success(request, f"Cohort Package '{item.package_name}' ({item.package_code}) created successfully.")
            return redirect('masters:package_detail', pk=item.pk)
    else:
        pkg_type = request.GET.get('type', '').upper()
        initial = {}
        if pkg_type in ['UMRA', 'HAJ']:
            initial['package_type'] = pkg_type
            if pkg_type == 'UMRA':
                initial['total_days'] = 15
                initial['medina_days'] = 7
                initial['makkah_p1_days'] = 8
                initial['makkah_p2_days'] = 0
                initial['mashair_days'] = 0
        form = CohortPackageForm(initial=initial)
        if hasattr(request, 'account') and request.account and 'cohort' in form.fields:
            form.fields['cohort'].queryset = Cohort.objects.filter(account=request.account, is_active=True)

    return render(request, 'masters/package_form.html', {
        'form': form,
        'title': 'New Cohort Package',
        'is_edit': False,
        'available_packages': available_packages,
    })


@login_required
def package_copy(request, pk):
    """Clone an existing package profile to create a new package with 1-click simplicity."""
    source_pkg = get_object_or_404(CohortPackage.objects.select_related('cohort'), pk=pk)

    available_packages = CohortPackage.objects.filter(is_active=True).select_related('cohort')
    if hasattr(request, 'account') and request.account:
        available_packages = available_packages.filter(cohort__account=request.account)

    if request.method == 'POST':
        form = CohortPackageForm(request.POST)
        if hasattr(request, 'account') and request.account and 'cohort' in form.fields:
            form.fields['cohort'].queryset = Cohort.objects.filter(account=request.account, is_active=True)
        if form.is_valid():
            new_pkg = form.save()
            log_audit_action(
                actor=request.user, action='CREATE', instance=new_pkg,
                account=getattr(new_pkg.cohort, 'account', getattr(request, 'account', None))
            )
            messages.success(
                request,
                f"Successfully cloned package profile '{new_pkg.package_name}' ({new_pkg.package_code}) from '{source_pkg.package_name}'."
            )
            return redirect('masters:package_detail', pk=new_pkg.pk)
    else:
        new_code = f"{source_pkg.package_code}-COPY"
        counter = 1
        while CohortPackage.objects.filter(cohort=source_pkg.cohort, package_code=new_code).exists():
            counter += 1
            new_code = f"{source_pkg.package_code}-COPY{counter}"

        initial_data = {
            'cohort': source_pkg.cohort,
            'package_type': source_pkg.package_type,
            'package_code': new_code,
            'package_name': f"{source_pkg.package_name} (Copy)",
            'total_days': source_pkg.total_days,
            'description': source_pkg.description,
            'airline': source_pkg.airline,
            'flight_route': source_pkg.flight_route,
            'flight_origin': source_pkg.flight_origin,
            'flight_destination': source_pkg.flight_destination,
            'medina_order': source_pkg.medina_order,
            'medina_days': source_pkg.medina_days,
            'medina_accn_type': source_pkg.medina_accn_type,
            'medina_hotel_name': source_pkg.medina_hotel_name,
            'medina_boarding': source_pkg.medina_boarding,
            'transfer_mode': source_pkg.transfer_mode,
            'makkah_p1_days': source_pkg.makkah_p1_days,
            'makkah_p1_accn_type': source_pkg.makkah_p1_accn_type,
            'makkah_p1_hotel_name': source_pkg.makkah_p1_hotel_name,
            'makkah_p1_boarding': source_pkg.makkah_p1_boarding,
            'makkah_p2_days': source_pkg.makkah_p2_days,
            'makkah_p2_accn_type': source_pkg.makkah_p2_accn_type,
            'makkah_p2_building_name': source_pkg.makkah_p2_building_name,
            'makkah_p2_boarding': source_pkg.makkah_p2_boarding,
            'mashair_days': source_pkg.mashair_days,
            'mina_maktab': source_pkg.mina_maktab,
            'mina_zone': source_pkg.mina_zone,
            'mashair_boarding': source_pkg.mashair_boarding,
            'arafat_details': source_pkg.arafat_details,
            'muzdalifah_details': source_pkg.muzdalifah_details,
            'post_haj_days': source_pkg.post_haj_days,
            'rate_double_sharing': source_pkg.rate_double_sharing,
            'rate_triple_sharing': source_pkg.rate_triple_sharing,
            'rate_quad_sharing': source_pkg.rate_quad_sharing,
            'is_active': True,
        }
        form = CohortPackageForm(initial=initial_data)
        if hasattr(request, 'account') and request.account and 'cohort' in form.fields:
            form.fields['cohort'].queryset = Cohort.objects.filter(account=request.account, is_active=True)

    return render(request, 'masters/package_form.html', {
        'form': form,
        'title': f"Copy Package Profile from '{source_pkg.package_name}'",
        'source_package': source_pkg,
        'is_copy': True,
        'available_packages': available_packages,
    })


@login_required
def package_update(request, pk):
    """Edit existing cohort package."""
    item = get_object_or_404(CohortPackage, pk=pk)
    available_packages = CohortPackage.objects.filter(is_active=True).exclude(pk=pk).select_related('cohort')
    if hasattr(request, 'account') and request.account:
        available_packages = available_packages.filter(cohort__account=request.account)

    if request.method == 'POST':
        form = CohortPackageForm(request.POST, instance=item)
        if hasattr(request, 'account') and request.account and 'cohort' in form.fields:
            form.fields['cohort'].queryset = Cohort.objects.filter(account=request.account, is_active=True)
        if form.is_valid():
            item = form.save()
            log_audit_action(
                actor=request.user, action='UPDATE', instance=item,
                account=getattr(item.cohort, 'account', getattr(request, 'account', None))
            )
            messages.success(request, f"Cohort Package '{item.package_name}' updated successfully.")
            return redirect('masters:package_detail', pk=item.pk)
    else:
        form = CohortPackageForm(instance=item)
        if hasattr(request, 'account') and request.account and 'cohort' in form.fields:
            form.fields['cohort'].queryset = Cohort.objects.filter(account=request.account, is_active=True)

    return render(request, 'masters/package_form.html', {
        'form': form,
        'item': item,
        'title': f"Edit Cohort Package: {item.package_name}",
        'is_edit': True,
        'available_packages': available_packages,
    })
pilgrim_list, pilgrim_create, pilgrim_update, pilgrim_toggle, pilgrim_bulk_delete = create_master_views(Pilgrim, PilgrimForm, 'Pilgrim', 'pilgrim')
tour_operator_list, tour_operator_create, tour_operator_update, tour_operator_toggle, tour_operator_bulk_delete = create_master_views(TourOperator, TourOperatorForm, 'Tour Operator', 'tour_operator')


# ==============================================================================
# COHORT PACKAGE & PILGRIM DYNAMIC DETAILS & AJAX
# ==============================================================================

@login_required
def package_detail(request, pk):
    """Detailed view for Haj / Umra Cohort Package showing full sequential itinerary."""
    package = get_object_or_404(CohortPackage.objects.select_related('cohort', 'cohort__account'), pk=pk)
    return render(request, 'masters/package_detail.html', {'package': package})


@login_required
def package_rates_api(request):
    """AJAX API returning package itinerary and auto-calculated costs for double/triple/quad sharing."""
    package_id = request.GET.get('package_id') or request.GET.get('package')
    sharing_type = (request.GET.get('sharing_type') or 'QUAD').upper()
    try:
        persons = int(request.GET.get('persons') or request.GET.get('family_members_count') or 1)
        if persons < 1:
            persons = 1
    except (ValueError, TypeError):
        persons = 1

    if not package_id:
        return JsonResponse({'error': 'package_id is required'}, status=400)

    package = get_object_or_404(CohortPackage, pk=package_id)
    if sharing_type == 'DOUBLE':
        rate = package.rate_double_sharing
    elif sharing_type == 'TRIPLE':
        rate = package.rate_triple_sharing
    else:
        rate = package.rate_quad_sharing

    total_cost = rate * Decimal(str(persons))

    return JsonResponse({
        'package_id': package.id,
        'package_code': package.package_code,
        'package_name': package.package_name,
        'cohort_title': package.cohort.title,
        'total_days': package.total_days,
        'airline': package.airline,
        'flight_route': package.get_flight_route_display(),
        'medina_hotel': package.medina_hotel_name,
        'medina_days': package.medina_days,
        'medina_boarding': package.get_medina_boarding_display(),
        'transfer_mode': package.get_transfer_mode_display(),
        'makkah_hotel': package.makkah_p1_hotel_name,
        'makkah_days': package.makkah_p1_days,
        'makkah_boarding': package.get_makkah_p1_boarding_display(),
        'makkah_building': package.makkah_p2_building_name,
        'mina_maktab': package.mina_maktab,
        'mina_zone': package.mina_zone,
        'rate_double': float(package.rate_double_sharing),
        'rate_triple': float(package.rate_triple_sharing),
        'rate_quad': float(package.rate_quad_sharing),
        'selected_rate': float(rate),
        'sharing_type': sharing_type,
        'persons': persons,
        'calculated_total': float(total_cost),
    })


@login_required
def packages_for_cohort(request):
    """Return HTMX option elements of packages for a selected cohort."""
    cohort_id = request.GET.get('cohort') or request.GET.get('cohort_id')
    packages = CohortPackage.objects.filter(cohort_id=cohort_id, is_active=True).order_by('package_name') if cohort_id else CohortPackage.objects.none()
    html = '<option value="">---------</option>'
    html += ''.join(f'<option value="{p.pk}">{p.package_code} - {p.package_name}</option>' for p in packages)
    return HttpResponse(html)


# ==============================================================================

# OPENING BALANCES (D4)
# ==============================================================================

import json

def _extract_sub_fund_breakdown(remarks):
    if not remarks or '[SUB_FUND_BREAKDOWN]' not in remarks:
        return {}
    try:
        raw = remarks.split('[SUB_FUND_BREAKDOWN]')[1].split('[/SUB_FUND_BREAKDOWN]')[0]
        return json.loads(raw)
    except Exception:
        return {}

def _pack_sub_fund_breakdown(user_note, breakdown_dict):
    clean_note = user_note or ''
    if '[SUB_FUND_BREAKDOWN]' in clean_note:
        clean_note = clean_note.split('[SUB_FUND_BREAKDOWN]')[0].strip()
    if breakdown_dict:
        summary_lines = [f"• {name}: Rs {Decimal(str(amt)):,.2f}" for name, amt in breakdown_dict.items() if Decimal(str(amt)) > 0]
        summary_text = "Sub-Fund Breakdown:\n" + "\n".join(summary_lines) if summary_lines else ""
        payload = json.dumps(breakdown_dict)
        if clean_note:
            return f"{clean_note}\n\n{summary_text}\n\n[SUB_FUND_BREAKDOWN]{payload}[/SUB_FUND_BREAKDOWN]".strip()
        else:
            return f"{summary_text}\n\n[SUB_FUND_BREAKDOWN]{payload}[/SUB_FUND_BREAKDOWN]".strip()
    return clean_note


@login_required
def opening_balance_list(request):
    account = request.account
    balances = OpeningBalance.objects.all().select_related('account', 'financial_year')
    if account:
        balances = balances.filter(account=account)
    return render(request, 'masters/opening_balance_list.html', {'balances': balances, 'selected_account': account})


@login_required
def opening_balance_create_or_edit(request, pk=None):
    from core.models import MajorHead, Account
    balance = get_object_or_404(OpeningBalance, pk=pk) if pk else None
    target_account = balance.account if balance else (request.account or Account.objects.first())

    acc_id = request.POST.get('account') or request.GET.get('account')
    if acc_id:
        try:
            target_account = Account.objects.get(pk=acc_id)
        except Account.DoesNotExist:
            pass

    all_major_heads = MajorHead.objects.all().order_by('name')
    sub_funds = all_major_heads.filter(account=target_account) if target_account else all_major_heads
    existing_breakdown = _extract_sub_fund_breakdown(balance.remarks) if balance else {}

    if request.method == 'POST':
        form = OpeningBalanceForm(request.POST, instance=balance)
        entry_mode = request.POST.get('entry_mode', 'complete')

        if form.is_valid():
            obj = form.save(commit=False)

            sub_fund_dict = {}
            sub_fund_total = Decimal('0.00')
            for mh in sub_funds:
                val = request.POST.get(f'sub_fund_{mh.id}', '').strip()
                if val:
                    try:
                        d_val = Decimal(val)
                        sub_fund_dict[mh.name] = str(d_val)
                        sub_fund_total += d_val
                    except Exception:
                        pass
                else:
                    sub_fund_dict[mh.name] = '0.00'

            if entry_mode == 'sub_fund' and sub_fund_total > Decimal('0.00'):
                obj.balance_amount = sub_fund_total
                obj.remarks = _pack_sub_fund_breakdown(form.cleaned_data.get('remarks', ''), sub_fund_dict)
            elif sub_fund_dict and any(Decimal(v) > 0 for v in sub_fund_dict.values()):
                obj.remarks = _pack_sub_fund_breakdown(form.cleaned_data.get('remarks', ''), sub_fund_dict)

            if 'confirm' in request.POST:
                obj.is_confirmed = True
                obj.confirmed_by = request.user
                obj.confirmed_at = timezone.now()
            obj.save()
            log_audit_action(actor=request.user, action='CONFIRM' if obj.is_confirmed else ('UPDATE' if balance else 'CREATE'), instance=obj, account=obj.account)
            messages.success(request, f"Opening balance for {obj.account.name} ({obj.financial_year.code}) saved.")
            return redirect('masters:opening_balance_list')
    else:
        init_remarks = balance.remarks if balance else ''
        if '[SUB_FUND_BREAKDOWN]' in init_remarks:
            init_remarks = init_remarks.split('[SUB_FUND_BREAKDOWN]')[0].strip()
        form = OpeningBalanceForm(instance=balance, initial={'account': target_account, 'financial_year': request.fy, 'remarks': init_remarks})

    from core.services import _resolve_sub_fund_opening_from_breakdown

    sub_fund_rows = []
    for mh in sub_funds:
        sub_ob = _resolve_sub_fund_opening_from_breakdown(mh, existing_breakdown)
        amt = str(sub_ob) if sub_ob is not None else '0.00'
        sub_fund_rows.append({
            'id': mh.id,
            'name': mh.name,
            'code': mh.code,
            'account_id': mh.account_id,
            'amount': amt,
        })

    account_sub_funds_map = {}
    for acc in Account.objects.all():
        account_sub_funds_map[str(acc.id)] = [
            {
                'id': mh.id,
                'name': mh.name,
                'code': mh.code,
                'amount': str(_resolve_sub_fund_opening_from_breakdown(mh, existing_breakdown) or '0.00') if (balance and balance.account_id == acc.id) else '0.00',
            }
            for mh in MajorHead.objects.filter(account=acc).order_by('display_order', 'name')
        ]

    return render(request, 'masters/opening_balance_form.html', {
        'form': form,
        'balance': balance,
        'title': 'Edit Opening Balance' if balance else 'New Opening Balance',
        'sub_funds': sub_funds,
        'sub_fund_rows': sub_fund_rows,
        'has_sub_fund_breakdown': bool(existing_breakdown),
        'account_sub_funds_json': json.dumps(account_sub_funds_map),
    })


@login_required
def opening_balance_bulk_delete(request):
    ids = _extract_ids(request)
    if not ids:
        messages.warning(request, "No opening balances selected for deletion.")
        return redirect('masters:opening_balance_list')

    deleted_count = 0
    for ob_id in ids:
        try:
            ob = OpeningBalance.objects.get(pk=ob_id)
            log_audit_action(actor=request.user, action='DELETE', instance=ob, account=ob.account)
            ob.delete()
            deleted_count += 1
        except OpeningBalance.DoesNotExist:
            continue

    if deleted_count > 0:
        messages.success(request, f"Successfully deleted {deleted_count} Opening Balance(s).")
    return redirect('masters:opening_balance_list')


