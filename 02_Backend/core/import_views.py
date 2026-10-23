from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import CreateView
from django.contrib import messages

from .models import ImportBatch
from .import_workflow import validate_frontend_batch, commit_frontend_batch
from .import_services import parse_import_file


class ImportBatchCreateWorkflowView(LoginRequiredMixin, CreateView):
    model = ImportBatch
    fields = ['source_file', 'source_type', 'remarks']
    template_name = 'finance/import_form.html'

    def form_valid(self, form):
        form.instance.account = self.request.account
        form.instance.imported_by = self.request.user
        response = super().form_valid(form)
        parse_import_file(self.object)
        return redirect('core:import_review', pk=self.object.pk)


class ImportBatchReviewView(LoginRequiredMixin, View):
    template_name = 'finance/import_review.html'

    def _batch(self, request, pk):
        batch = get_object_or_404(ImportBatch, pk=pk, account=request.account)
        if batch.imported_by_id != request.user.id and getattr(getattr(request.user, 'profile', None), 'role', '') not in ['ADMINISTRATOR', 'MANAGEMENT']:
            raise PermissionDenied('You are not authorised to review this import batch.')
        return batch

    def get(self, request, pk):
        batch = self._batch(request, pk)
        first = batch.records.order_by('original_row_number').first()
        headers = list(first.row_data.keys()) if first else []
        return render(request, self.template_name, {'batch': batch, 'headers': headers, 'records': batch.records.order_by('original_row_number')[:100], 'mapping': {}})

    def post(self, request, pk):
        batch = self._batch(request, pk)
        mapping = {k: request.POST.get(k) for k in ['date', 'amount', 'head_code', 'reference', 'description', 'direction', 'unit', 'section', 'nature']}
        mapping = {k: v for k, v in mapping.items() if v}
        action = request.POST.get('action', 'validate')
        if action == 'validate':
            result = validate_frontend_batch(batch, mapping)
            messages.success(request, f"Validation complete: {result['valid']} valid, {result['failed']} invalid, {result['duplicates']} duplicate candidate(s).")
        elif action == 'commit':
            imported = commit_frontend_batch(batch, mapping)
            messages.success(request, f'{imported} transaction(s) imported successfully.')
        return redirect('core:import_review', pk=batch.pk)
