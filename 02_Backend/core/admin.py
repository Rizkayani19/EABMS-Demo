from django.contrib import admin
from .models import (
    Installation, Account, FinancialYear, Unit, MajorHead, SubHead,
    InflowType, OutflowNature, BudgetType, ReimbursementType, DocumentType,
    PersonnelClassification, AccountHead, OpeningBalance, AuditLog, UserProfile,
    Budget, BudgetLine, BudgetRevision
)
from .future_budget_management_models import FutureBudgetManagementInput


@admin.register(Installation)
class InstallationAdmin(admin.ModelAdmin):
    list_display = ('installation_code', 'installation_name', 'is_active', 'created_at')
    search_fields = ('installation_code', 'installation_name')


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'installation', 'is_active', 'display_order', 'created_at')
    list_filter = ('is_active', 'installation')
    search_fields = ('name', 'code')
    ordering = ('display_order', 'name')


@admin.register(FinancialYear)
class FinancialYearAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'start_date', 'end_date', 'status', 'display_order')
    list_filter = ('status',)
    search_fields = ('code', 'name')
    ordering = ('-start_date',)


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active', 'display_order')
    list_filter = ('is_active',)
    search_fields = ('name', 'code')


@admin.register(MajorHead)
class MajorHeadAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'account', 'is_active', 'display_order')
    list_filter = ('account', 'is_active')
    search_fields = ('name', 'code')


@admin.register(SubHead)
class SubHeadAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'major_head', 'account', 'is_active', 'display_order')
    list_filter = ('account', 'is_active', 'major_head')
    search_fields = ('name', 'code')


@admin.register(InflowType)
class InflowTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active', 'display_order')
    list_filter = ('is_active',)
    search_fields = ('name', 'code')


@admin.register(OutflowNature)
class OutflowNatureAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_pass_through', 'is_active', 'display_order')
    list_filter = ('is_active', 'is_pass_through')
    search_fields = ('name', 'code')


@admin.register(BudgetType)
class BudgetTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active', 'display_order')
    list_filter = ('is_active',)
    search_fields = ('name', 'code')


@admin.register(ReimbursementType)
class ReimbursementTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active', 'display_order')
    list_filter = ('is_active',)
    search_fields = ('name', 'code')


@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active', 'display_order')
    list_filter = ('is_active',)
    search_fields = ('name', 'code')


@admin.register(PersonnelClassification)
class PersonnelClassificationAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active', 'display_order')
    list_filter = ('is_active',)
    search_fields = ('name', 'code')


@admin.register(AccountHead)
class AccountHeadAdmin(admin.ModelAdmin):
    list_display = ('name', 'account', 'head_type', 'major_head', 'sub_head', 'code', 'is_active', 'display_order')
    list_filter = ('account', 'head_type', 'is_active')
    search_fields = ('name', 'code', 'account__name')
    ordering = ('account', 'display_order', 'name')


@admin.register(OpeningBalance)
class OpeningBalanceAdmin(admin.ModelAdmin):
    list_display = ('account', 'financial_year', 'balance_amount', 'is_confirmed', 'confirmed_by', 'confirmed_at')
    list_filter = ('account', 'financial_year', 'is_confirmed')
    search_fields = ('account__name', 'financial_year__code')


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'actor', 'account', 'action', 'model_name', 'record_id', 'record_repr')
    list_filter = ('action', 'model_name', 'account')
    search_fields = ('record_id', 'record_repr', 'actor__username')
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'default_account', 'is_active')
    list_filter = ('role', 'is_active', 'default_account')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'user__email')


class BudgetLineInline(admin.TabularInline):
    model = BudgetLine
    extra = 1


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ('account', 'financial_year', 'status', 'reference')
    list_filter = ('status', 'account', 'financial_year')
    search_fields = ('reference', 'remarks')
    ordering = ('account', '-financial_year__start_date')
    inlines = [BudgetLineInline]


@admin.register(BudgetRevision)
class BudgetRevisionAdmin(admin.ModelAdmin):
    list_display = ('budget_line', 'previous_amount', 'revised_amount', 'difference', 'revised_by', 'revised_at')
    list_filter = ('revised_at',)
    search_fields = ('budget_line__account_head__name', 'reason', 'reference')
    readonly_fields = ('revised_at',)


@admin.register(FutureBudgetManagementInput)
class FutureBudgetManagementInputAdmin(admin.ModelAdmin):
    list_display = (
        'future_budget', 'account_head', 'input_type', 'amount', 'status',
        'created_by', 'created_at'
    )
    list_filter = ('input_type', 'status', 'future_budget')
    search_fields = ('description', 'justification', 'reference', 'account_head__name')
    filter_horizontal = ('units', 'internal_sections')
    readonly_fields = ('created_at', 'updated_at')
