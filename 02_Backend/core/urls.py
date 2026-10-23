from django.urls import path
from . import views
from .balance_report_views import (
    PresentBalanceSubFundReportView,
    PresentBalanceAccountHeadReportView,
    PresentBalanceSubAccountHeadReportView,
)
from .transaction_views import (
    TransactionListView, InflowCreateView, OutflowCreateView, InternalTransferCreateView,
    TransactionDetailView, TransactionUpdateView, TransactionInlineUpdateView,
    ReimbursementListView, ReimbursementCreateView, ReimbursementUpdateView,
    load_sub_heads, load_account_heads,
)
from .transaction_cancel_views import TransactionCancelView
from .bulk_transactions import TransactionBulkEditView, TransactionBulkSaveView
from .bulk_views import (
    TransactionBulkDeleteView,
    ReimbursementBulkDeleteView,
    BudgetBulkDeleteView,
    BudgetLineBulkDeleteView,
    FutureBudgetBulkDeleteView,
    FutureBudgetLineBulkDeleteView,
    FutureBudgetKnownChangeBulkDeleteView,
    FutureBudgetPersonnelBulkDeleteView,
)
from .data_admin import TransactionDataAdministrationView, TransactionRestoreView
from .import_views import ImportBatchCreateWorkflowView, ImportBatchReviewView
from .budget_views import (
    BudgetListView, BudgetCreateView, BudgetDetailView, BudgetUpdateView,
    BudgetDeleteView,
    BudgetLineCreateView, BudgetRevisionCreateView,
)
from .future_budget_allocation_views import FutureBudgetAllocationView
from .historical_budget_allocation_views import HistoricalBudgetAllocationView
from .future_budget_crud_views import (
    FutureBudgetBuildView, FutureBudgetCreateView, FutureBudgetDetailView,
    FutureBudgetDeleteView, FutureBudgetUpdateView,
    FutureBudgetListView, FutureBudgetLineUpdateView,
    KnownChangeCreateView, PersonnelPlanView,
)
from .future_budget_exports import (
    FutureBudgetPDFExportView, FutureBudgetExcelExportView, FutureBudgetWordExportView,
)
from .future_budget_review_views import (
    FutureBudgetReviewView, FutureBudgetReviewBuildView,
    FutureBudgetManagementInputCreateView,
)
from .future_budget_proposal_views import (
    FutureBudgetLineProposalView, FutureBudgetClearProposalView,
    FutureBudgetBulkCopySuggestedView, FutureBudgetBulkProposalSaveView,
)
from .future_budget_inflow_proposal_views import FutureBudgetInflowProposalView
from .future_budget_workflow_views import (
    FutureBudgetProposeView, FutureBudgetApproveView, FutureBudgetRevertDraftView,
)
from .access_control import (
    force_active_account_filters, transaction_view, scoped_reimbursement,
    scoped_budget, scoped_budget_line, scoped_future_budget,
    scoped_future_budget_line, scoped_document, scoped_account_head_ajax,
)
from .future_planning_views import FutureBudgetPlanningView

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('reports/present-balance/sub-fund/', PresentBalanceSubFundReportView.as_view(), name='present_balance_sub_fund'),
    path('reports/present-balance/account-head/', PresentBalanceAccountHeadReportView.as_view(), name='present_balance_account_head'),
    path('reports/present-balance/sub-account-head/', PresentBalanceSubAccountHeadReportView.as_view(), name='present_balance_sub_account_head'),
    path('transactions/', force_active_account_filters(TransactionListView.as_view()), name='transaction_list'),
    path('transactions/inflow/new/', InflowCreateView.as_view(), name='inflow_create'),
    path('transactions/outflow/new/', OutflowCreateView.as_view(), name='outflow_create'),
    path('transactions/transfers/', InternalTransferCreateView.as_view(), name='internal_transfer_hub'),
    path('transactions/transfer/new/', InternalTransferCreateView.as_view(), name='internal_transfer_create'),
    path('transactions/bulk-edit/', TransactionBulkEditView.as_view(), name='transaction_bulk_edit'),
    path('transactions/bulk-save/', TransactionBulkSaveView.as_view(), name='transaction_bulk_save'),
    path('transactions/bulk-delete/', TransactionBulkDeleteView.as_view(), name='transaction_bulk_delete'),
    path('transactions/<uuid:pk>/', transaction_view(TransactionDetailView.as_view()), name='transaction_detail'),
    path('transactions/<uuid:pk>/edit/', transaction_view(TransactionUpdateView.as_view()), name='transaction_edit'),
    path('transactions/<uuid:pk>/inline-update/', transaction_view(TransactionInlineUpdateView.as_view()), name='transaction_inline_update'),
    path('transactions/<uuid:pk>/cancel/', transaction_view(TransactionCancelView.as_view()), name='transaction_cancel'),
    path('transactions/ajax/load-sub-heads/', scoped_account_head_ajax(load_sub_heads), name='load_sub_heads'),
    path('transactions/ajax/load-account-heads/', load_account_heads, name='load_account_heads'),
    path('reimbursements/', ReimbursementListView.as_view(), name='reimbursement_list'),
    path('reimbursements/new/', ReimbursementCreateView.as_view(), name='reimbursement_create'),
    path('reimbursements/bulk-delete/', ReimbursementBulkDeleteView.as_view(), name='reimbursement_bulk_delete'),
    path('reimbursements/<uuid:pk>/edit/', scoped_reimbursement(ReimbursementUpdateView.as_view()), name='reimbursement_edit'),
    path('data-administration/', TransactionDataAdministrationView.as_view(), name='data_administration'),
    path('data-administration/transactions/<uuid:pk>/restore/', TransactionRestoreView.as_view(), name='transaction_restore'),
    path('imports/new/', ImportBatchCreateWorkflowView.as_view(), name='import_create'),
    path('imports/<int:pk>/review/', ImportBatchReviewView.as_view(), name='import_review'),
    path('budgets/', BudgetListView.as_view(), name='budget_list'),
    path('budgets/new/', BudgetCreateView.as_view(), name='budget_create'),
    path('budgets/bulk-delete/', BudgetBulkDeleteView.as_view(), name='budget_bulk_delete'),
    path('budgets/<int:pk>/', scoped_budget(BudgetDetailView.as_view()), name='budget_detail'),
    path('budgets/<int:pk>/edit/', scoped_budget(BudgetUpdateView.as_view()), name='budget_edit'),
    path('budgets/<int:pk>/delete/', BudgetDeleteView.as_view(), name='budget_delete'),
    path('budgets/<int:budget_id>/lines/new/', scoped_budget(BudgetLineCreateView.as_view()), name='budgetline_create'),
    path('budgets/<int:budget_id>/lines/bulk-delete/', BudgetLineBulkDeleteView.as_view(), name='budgetline_bulk_delete'),
    path('budgets/lines/<int:line_id>/revise/', scoped_budget_line(BudgetRevisionCreateView.as_view()), name='budgetrevision_create'),
    path('budgets/lines/<int:line_id>/historical-allocations/', HistoricalBudgetAllocationView.as_view(), name='historical_budget_allocation'),
    path('documents/upload/', views.DocumentUploadView.as_view(), name='document_upload'),
    path('documents/<int:pk>/download/', scoped_document(views.SecureDocumentDownloadView.as_view()), name='document_download'),
    path('future-budgets/', FutureBudgetListView.as_view(), name='future_budget_list'),
    path('future-budgets/new/', FutureBudgetCreateView.as_view(), name='future_budget_create'),
    path('future-budgets/bulk-delete/', FutureBudgetBulkDeleteView.as_view(), name='future_budget_bulk_delete'),
    path('future-budgets/<int:future_budget_id>/lines/bulk-delete/', FutureBudgetLineBulkDeleteView.as_view(), name='future_budget_line_bulk_delete'),
    path('future-budgets/known-changes/bulk-delete/', FutureBudgetKnownChangeBulkDeleteView.as_view(), name='future_budget_known_change_bulk_delete'),
    path('future-budgets/personnel/bulk-delete/', FutureBudgetPersonnelBulkDeleteView.as_view(), name='future_budget_personnel_bulk_delete'),
    path('future-budgets/<int:pk>/', scoped_future_budget(FutureBudgetDetailView.as_view()), name='future_budget_detail'),
    path('future-budgets/<int:pk>/edit/', scoped_future_budget(FutureBudgetUpdateView.as_view()), name='future_budget_edit'),
    path('future-budgets/<int:pk>/delete/', FutureBudgetDeleteView.as_view(), name='future_budget_delete'),
    path('future-budgets/<int:pk>/review/', scoped_future_budget(FutureBudgetReviewView.as_view()), name='future_budget_review'),
    path('future-budgets/<int:pk>/review/recalculate/', scoped_future_budget(FutureBudgetReviewBuildView.as_view()), name='future_budget_review_build'),
    path('future-budgets/<int:pk>/review/copy-suggested/', scoped_future_budget(FutureBudgetBulkCopySuggestedView.as_view()), name='future_budget_copy_suggested'),
    path('future-budgets/<int:pk>/review/save-all-proposals/', scoped_future_budget(FutureBudgetBulkProposalSaveView.as_view()), name='future_budget_save_all_proposals'),
    path('future-budgets/<int:pk>/review/inflow-proposal/', scoped_future_budget(FutureBudgetInflowProposalView.as_view()), name='future_budget_inflow_proposal'),
    path('future-budgets/<int:pk>/review/management-input/', scoped_future_budget(FutureBudgetManagementInputCreateView.as_view()), name='future_budget_management_input_create'),
    path('future-budgets/lines/<int:pk>/edit/', scoped_future_budget_line(FutureBudgetLineUpdateView.as_view()), name='future_budget_line_edit'),
    path('future-budgets/lines/<int:pk>/proposal/', scoped_future_budget_line(FutureBudgetLineProposalView.as_view()), name='future_budget_line_proposal'),
    path('future-budgets/lines/<int:pk>/proposal/clear/', scoped_future_budget_line(FutureBudgetClearProposalView.as_view()), name='future_budget_line_proposal_clear'),
    path('future-budgets/lines/<int:pk>/allocations/', scoped_future_budget_line(FutureBudgetAllocationView.as_view()), name='future_budget_allocation'),
    path('future-budgets/<int:budget_id>/known-changes/new/', scoped_future_budget(KnownChangeCreateView.as_view()), name='known_change_create'),
    path('future-budgets/<int:pk>/personnel/', scoped_future_budget(PersonnelPlanView.as_view()), name='personnel_plan'),
    path('future-budgets/<int:pk>/propose/', scoped_future_budget(FutureBudgetProposeView.as_view()), name='propose_future_budget'),
    path('future-budgets/<int:pk>/revert-draft/', scoped_future_budget(FutureBudgetRevertDraftView.as_view()), name='revert_future_budget_draft'),
    path('future-budgets/<int:pk>/approve/', scoped_future_budget(FutureBudgetApproveView.as_view()), name='approve_future_budget'),
    path('future-budgets/<int:pk>/build/', scoped_future_budget(FutureBudgetBuildView.as_view()), name='future_budget_build'),
    path('future-budgets/<int:pk>/pdf/', scoped_future_budget(FutureBudgetPDFExportView.as_view()), name='future_budget_pdf'),
    path('future-budgets/<int:pk>/excel/', scoped_future_budget(FutureBudgetExcelExportView.as_view()), name='future_budget_excel'),
    path('future-budgets/<int:pk>/word/', scoped_future_budget(FutureBudgetWordExportView.as_view()), name='future_budget_word'),
    path('future-budget/planning/', FutureBudgetPlanningView.as_view(), name='future_budget_planning'),
    path('reconcile-opening-balance/', views.reconcile_opening_balance, name='reconcile_opening_balance'),
    path('reconcile-balance/', views.reconcile_opening_balance, name='reconcile_balance'),
    path('manifest.webmanifest', views.web_manifest, name='web_manifest'),
    path('backup/trigger/', views.trigger_backup, name='trigger_backup'),
]
