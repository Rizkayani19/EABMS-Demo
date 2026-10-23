from django.contrib import admin

from .models import InternalSection, UnitSectionResponsibility


@admin.register(InternalSection)
class InternalSectionAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'is_active', 'display_order')
    list_filter = ('is_active',)
    search_fields = ('code', 'name', 'description')
    ordering = ('display_order', 'name')


@admin.register(UnitSectionResponsibility)
class UnitSectionResponsibilityAdmin(admin.ModelAdmin):
    list_display = ('unit', 'section', 'is_primary', 'is_active')
    list_filter = ('is_primary', 'is_active', 'section')
    search_fields = ('unit__name', 'unit__code', 'section__name', 'section__code')
