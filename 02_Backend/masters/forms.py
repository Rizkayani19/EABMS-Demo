from decimal import Decimal
from django import forms
from core.models import (
    Installation, Account, FinancialYear, Unit, MajorHead, SubHead,
    InflowType, OutflowNature, BudgetType, ReimbursementType, DocumentType,
    PersonnelClassification, AccountHead, OpeningBalance
)

INPUT_CSS = "w-full px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 text-sm"
SELECT_CSS = "w-full px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 text-sm bg-white"
CHECKBOX_CSS = "h-4 w-4 text-emerald-600 focus:ring-emerald-500 border-slate-300 rounded"
TEXTAREA_CSS = "w-full px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 text-sm"


class InstallationForm(forms.ModelForm):
    class Meta:
        model = Installation
        fields = ['installation_code', 'installation_name', 'description', 'is_active']
        widgets = {
            'installation_code': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. INST-01'}),
            'installation_name': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. ABMS Main Installation'}),
            'description': forms.Textarea(attrs={'class': TEXTAREA_CSS, 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': CHECKBOX_CSS}),
        }


class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ['installation', 'code', 'name', 'short_name', 'budget_allocation_basis', 'description', 'display_order', 'is_active']
        widgets = {
            'installation': forms.Select(attrs={'class': SELECT_CSS}),
            'code': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. NGL'}),
            'name': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. NexGen Holdings Ltd.'}),
            'short_name': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. NGL'}),
            'budget_allocation_basis': forms.Select(attrs={'class': SELECT_CSS}),
            'description': forms.Textarea(attrs={'class': TEXTAREA_CSS, 'rows': 3}),
            'display_order': forms.NumberInput(attrs={'class': INPUT_CSS, 'min': 1}),
            'is_active': forms.CheckboxInput(attrs={'class': CHECKBOX_CSS}),
        }


class FinancialYearForm(forms.ModelForm):
    class Meta:
        model = FinancialYear
        fields = ['code', 'name', 'start_date', 'end_date', 'status', 'display_order']
        widgets = {
            'code': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. 2026-27'}),
            'name': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. FY 2026-27'}),
            'start_date': forms.DateInput(attrs={'class': INPUT_CSS, 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': INPUT_CSS, 'type': 'date'}),
            'status': forms.Select(attrs={'class': SELECT_CSS}),
            'display_order': forms.NumberInput(attrs={'class': INPUT_CSS, 'min': 1}),
        }


class UnitForm(forms.ModelForm):
    class Meta:
        model = Unit
        fields = ['code', 'name', 'description', 'display_order', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. BR-NORTH'}),
            'name': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. Northern Branch'}),
            'description': forms.Textarea(attrs={'class': TEXTAREA_CSS, 'rows': 3}),
            'display_order': forms.NumberInput(attrs={'class': INPUT_CSS, 'min': 1}),
            'is_active': forms.CheckboxInput(attrs={'class': CHECKBOX_CSS}),
        }


class MajorHeadForm(forms.ModelForm):
    class Meta:
        model = MajorHead
        fields = ['account', 'code', 'name', 'description', 'display_order', 'is_active']
        widgets = {
            'account': forms.Select(attrs={'class': SELECT_CSS}),
            'code': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. MH-01'}),
            'name': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. Operational Expenditures'}),
            'description': forms.Textarea(attrs={'class': TEXTAREA_CSS, 'rows': 3}),
            'display_order': forms.NumberInput(attrs={'class': INPUT_CSS, 'min': 1}),
            'is_active': forms.CheckboxInput(attrs={'class': CHECKBOX_CSS}),
        }
        labels = {
            'name': 'Sub Fund Name (Tier 1)',
            'code': 'Sub Fund Code',
        }

    def __init__(self, *args, **kwargs):
        account = kwargs.pop('account', None)
        super().__init__(*args, **kwargs)
        if account:
            self.fields['account'].initial = account
            self.fields['account'].queryset = Account.objects.filter(pk=account.pk)


class SubHeadForm(forms.ModelForm):
    class Meta:
        model = SubHead
        fields = ['account', 'major_head', 'account_head', 'code', 'name', 'description', 'display_order', 'is_active']
        widgets = {
            'account': forms.Select(attrs={'class': SELECT_CSS}),
            'major_head': forms.Select(attrs={'class': SELECT_CSS}),
            'account_head': forms.Select(attrs={'class': SELECT_CSS}),
            'code': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. SH-01'}),
            'name': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. Utilities'}),
            'description': forms.Textarea(attrs={'class': TEXTAREA_CSS, 'rows': 3}),
            'display_order': forms.NumberInput(attrs={'class': INPUT_CSS, 'min': 1}),
            'is_active': forms.CheckboxInput(attrs={'class': CHECKBOX_CSS}),
        }
        labels = {
            'major_head': 'Sub Fund (Tier 1)',
            'account_head': 'Account Head (Tier 2)',
            'name': 'Sub Head Name (Tier 3)',
        }

    def __init__(self, *args, **kwargs):
        account = kwargs.pop('account', None)
        super().__init__(*args, **kwargs)
        if account:
            self.fields['account'].initial = account
            self.fields['account'].queryset = Account.objects.filter(pk=account.pk)
            self.fields['major_head'].queryset = MajorHead.objects.filter(account=account).order_by('name')
            self.fields['account_head'].queryset = AccountHead.objects.filter(account=account).order_by('name')
        self.fields['major_head'].label = 'Sub Fund (Tier 1)'
        self.fields['account_head'].label = 'Account Head (Tier 2)'
        self.fields['name'].label = 'Sub Head Name (Tier 3)'


class InflowTypeForm(forms.ModelForm):
    class Meta:
        model = InflowType
        fields = ['account', 'code', 'name', 'description', 'display_order', 'is_active']
        widgets = {
            'account': forms.Select(attrs={'class': SELECT_CSS}),
            'code': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. DIRECT'}),
            'name': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. Direct Inflow'}),
            'description': forms.Textarea(attrs={'class': TEXTAREA_CSS, 'rows': 3}),
            'display_order': forms.NumberInput(attrs={'class': INPUT_CSS, 'min': 1}),
            'is_active': forms.CheckboxInput(attrs={'class': CHECKBOX_CSS}),
        }


class OutflowNatureForm(forms.ModelForm):
    class Meta:
        model = OutflowNature
        fields = ['account', 'code', 'name', 'is_pass_through', 'description', 'display_order', 'is_active']
        widgets = {
            'account': forms.Select(attrs={'class': SELECT_CSS}),
            'code': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. ROUTINE'}),
            'name': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. Routine'}),
            'is_pass_through': forms.CheckboxInput(attrs={'class': CHECKBOX_CSS}),
            'description': forms.Textarea(attrs={'class': TEXTAREA_CSS, 'rows': 3}),
            'display_order': forms.NumberInput(attrs={'class': INPUT_CSS, 'min': 1}),
            'is_active': forms.CheckboxInput(attrs={'class': CHECKBOX_CSS}),
        }


class BudgetTypeForm(forms.ModelForm):
    class Meta:
        model = BudgetType
        fields = ['code', 'name', 'description', 'display_order', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. INITIAL'}),
            'name': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. Initial Approved Budget'}),
            'description': forms.Textarea(attrs={'class': TEXTAREA_CSS, 'rows': 3}),
            'display_order': forms.NumberInput(attrs={'class': INPUT_CSS, 'min': 1}),
            'is_active': forms.CheckboxInput(attrs={'class': CHECKBOX_CSS}),
        }


class ReimbursementTypeForm(forms.ModelForm):
    class Meta:
        model = ReimbursementType
        fields = ['code', 'name', 'description', 'display_order', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. SIB_REIMBURSEMENT'}),
            'name': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. HQO Recoupment'}),
            'description': forms.Textarea(attrs={'class': TEXTAREA_CSS, 'rows': 3}),
            'display_order': forms.NumberInput(attrs={'class': INPUT_CSS, 'min': 1}),
            'is_active': forms.CheckboxInput(attrs={'class': CHECKBOX_CSS}),
        }


class DocumentTypeForm(forms.ModelForm):
    class Meta:
        model = DocumentType
        fields = ['code', 'name', 'description', 'display_order', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. SANCTION_LETTER'}),
            'name': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. Sanction Letter'}),
            'description': forms.Textarea(attrs={'class': TEXTAREA_CSS, 'rows': 3}),
            'display_order': forms.NumberInput(attrs={'class': INPUT_CSS, 'min': 1}),
            'is_active': forms.CheckboxInput(attrs={'class': CHECKBOX_CSS}),
        }


class PersonnelClassificationForm(forms.ModelForm):
    class Meta:
        model = PersonnelClassification
        fields = ['code', 'name', 'description', 'display_order', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. CONTRACT_CIVILIAN'}),
            'name': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. Contract Civilian Staff'}),
            'description': forms.Textarea(attrs={'class': TEXTAREA_CSS, 'rows': 3}),
            'display_order': forms.NumberInput(attrs={'class': INPUT_CSS, 'min': 1}),
            'is_active': forms.CheckboxInput(attrs={'class': CHECKBOX_CSS}),
        }


class AccountHeadForm(forms.ModelForm):
    class Meta:
        model = AccountHead
        fields = ['account', 'major_head', 'sub_head', 'code', 'name', 'head_type', 'description', 'display_order', 'is_active']
        widgets = {
            'account': forms.Select(attrs={'class': SELECT_CSS}),
            'major_head': forms.Select(attrs={'class': SELECT_CSS}),
            'sub_head': forms.Select(attrs={'class': SELECT_CSS}),
            'code': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. NGL-01'}),
            'name': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. Utility / Maint'}),
            'head_type': forms.Select(attrs={'class': SELECT_CSS}),
            'description': forms.Textarea(attrs={'class': TEXTAREA_CSS, 'rows': 3, 'placeholder': 'Optional description...'}),
            'display_order': forms.NumberInput(attrs={'class': INPUT_CSS, 'min': 1}),
            'is_active': forms.CheckboxInput(attrs={'class': CHECKBOX_CSS}),
        }

    def __init__(self, *args, **kwargs):
        account = kwargs.pop('account', None)
        super().__init__(*args, **kwargs)
        
        self.fields['account'].widget.attrs.update({
            'hx-get': '/masters/sub-head-options/',
            'hx-target': '#id_sub_head', 
            'hx-trigger': 'change',
            'hx-include': "[name='account']",
        })
        
        if account:
            self.fields['account'].initial = account
            self.fields['account'].queryset = Account.objects.filter(pk=account.pk)
            self.fields['sub_head'].queryset = SubHead.objects.filter(account=account).order_by('name')
            self.fields['major_head'].queryset = MajorHead.objects.filter(account=account).order_by('name')
        self.fields['major_head'].label = 'Sub Fund (Tier 1)'
        self.fields['name'].label = 'Account Head Name (Tier 2)'
        self.fields['sub_head'].label = 'Default Sub Head (Optional)'

class OpeningBalanceForm(forms.ModelForm):
    class Meta:
        model = OpeningBalance
        fields = ['account', 'financial_year', 'balance_amount', 'reference', 'remarks', 'document_reference']
        widgets = {
            'account': forms.Select(attrs={'class': SELECT_CSS}),
            'financial_year': forms.Select(attrs={'class': SELECT_CSS}),
            'balance_amount': forms.NumberInput(attrs={'class': INPUT_CSS, 'step': '0.01'}),
            'reference': forms.TextInput(attrs={'class': INPUT_CSS}),
            'remarks': forms.Textarea(attrs={'class': TEXTAREA_CSS, 'rows': 3, 'placeholder': 'Mandatory if adjusting from proposed balance...'}),
            'document_reference': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'Supporting document tracking ID'}),
        }


from .models import City, CeremonyVenue, CeremonyEvent, Cohort, CohortPackage, Pilgrim, TourOperator

class CityForm(forms.ModelForm):
    class Meta:
        model = City
        fields = ['name', 'province', 'display_order', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. Lahore'}),
            'province': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. Punjab'}),
            'display_order': forms.NumberInput(attrs={'class': INPUT_CSS, 'min': 1}),
            'is_active': forms.CheckboxInput(attrs={'class': CHECKBOX_CSS}),
        }


class CeremonyVenueForm(forms.ModelForm):
    class Meta:
        model = CeremonyVenue
        fields = ['code', 'name', 'city', 'description', 'display_order', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. SPG'}),
            'name': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. Shakarparian Ceremony Ground'}),
            'city': forms.Select(attrs={'class': SELECT_CSS}),
            'description': forms.Textarea(attrs={'class': TEXTAREA_CSS, 'rows': 3}),
            'display_order': forms.NumberInput(attrs={'class': INPUT_CSS, 'min': 1}),
            'is_active': forms.CheckboxInput(attrs={'class': CHECKBOX_CSS}),
        }


class CeremonyEventForm(forms.ModelForm):
    class Meta:
        model = CeremonyEvent
        fields = ['account', 'event_year', 'name', 'major_head', 'venue', 'description', 'is_active']
        widgets = {
            'account': forms.Select(attrs={'class': SELECT_CSS}),
            'event_year': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. 2026'}),
            'name': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. Pak Day Ceremony'}),
            'major_head': forms.Select(attrs={'class': SELECT_CSS}),
            'venue': forms.Select(attrs={'class': SELECT_CSS}),
            'description': forms.Textarea(attrs={'class': TEXTAREA_CSS, 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': CHECKBOX_CSS}),
        }


class CohortForm(forms.ModelForm):
    class Meta:
        model = Cohort
        fields = ['account', 'cohort_type', 'code', 'title', 'cycle_label', 'start_date', 'end_date', 'is_active']
        widgets = {
            'account': forms.Select(attrs={'class': SELECT_CSS}),
            'cohort_type': forms.Select(attrs={'class': SELECT_CSS}),
            'code': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. HJC-2026 or UMC-01 (2025-26)'}),
            'title': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. Hajj Cohort 2026'}),
            'cycle_label': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. 2026 / 2025-26'}),
            'start_date': forms.DateInput(attrs={'class': INPUT_CSS, 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': INPUT_CSS, 'type': 'date'}),
            'is_active': forms.CheckboxInput(attrs={'class': CHECKBOX_CSS}),
        }


class CohortPackageForm(forms.ModelForm):
    class Meta:
        model = CohortPackage
        fields = [
            'cohort', 'package_type', 'package_code', 'package_name', 'total_days', 'description',
            'airline', 'flight_route', 'flight_origin', 'flight_destination',
            'medina_order', 'medina_days', 'medina_accn_type', 'medina_hotel_name', 'medina_boarding',
            'transfer_mode',
            'makkah_p1_days', 'makkah_p1_accn_type', 'makkah_p1_hotel_name', 'makkah_p1_boarding',
            'makkah_p2_days', 'makkah_p2_accn_type', 'makkah_p2_building_name', 'makkah_p2_boarding',
            'mashair_days', 'mina_maktab', 'mina_zone', 'mashair_boarding', 'arafat_details', 'muzdalifah_details',
            'post_haj_days',
            'rate_double_sharing', 'rate_triple_sharing', 'rate_quad_sharing',
            'is_active'
        ]
        widgets = {
            'cohort': forms.Select(attrs={'class': SELECT_CSS}),
            'package_type': forms.Select(attrs={'class': SELECT_CSS, 'id': 'id_package_type'}),
            'package_code': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. HJC-2027-ECO or UMC-01-STD'}),
            'package_name': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. Economy Package'}),
            'total_days': forms.NumberInput(attrs={'class': INPUT_CSS, 'min': 1}),
            'description': forms.Textarea(attrs={'class': TEXTAREA_CSS, 'rows': 2}),
            'airline': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. PIA, Saudia'}),
            'flight_route': forms.Select(attrs={'class': SELECT_CSS}),
            'flight_origin': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. Islamabad (ISB)'}),
            'flight_destination': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. Medina (MED) / Jeddah (JED)'}),
            'medina_order': forms.Select(attrs={'class': SELECT_CSS}),
            'medina_days': forms.NumberInput(attrs={'class': INPUT_CSS, 'min': 0}),
            'medina_accn_type': forms.Select(attrs={'class': SELECT_CSS}),
            'medina_hotel_name': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. Leader Al Muna Kareem'}),
            'medina_boarding': forms.Select(attrs={'class': SELECT_CSS}),
            'transfer_mode': forms.Select(attrs={'class': SELECT_CSS}),
            'makkah_p1_days': forms.NumberInput(attrs={'class': INPUT_CSS, 'min': 0}),
            'makkah_p1_accn_type': forms.Select(attrs={'class': SELECT_CSS}),
            'makkah_p1_hotel_name': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. Swissotel Al Maqam'}),
            'makkah_p1_boarding': forms.Select(attrs={'class': SELECT_CSS}),
            'makkah_p2_days': forms.NumberInput(attrs={'class': INPUT_CSS, 'min': 0}),
            'makkah_p2_accn_type': forms.Select(attrs={'class': SELECT_CSS}),
            'makkah_p2_building_name': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. Azizia Building A-3'}),
            'makkah_p2_boarding': forms.Select(attrs={'class': SELECT_CSS}),
            'mashair_days': forms.NumberInput(attrs={'class': INPUT_CSS, 'min': 0}),
            'mina_maktab': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. Maktab A, Maktab B'}),
            'mina_zone': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. Zone 1, Zone 2'}),
            'mashair_boarding': forms.Select(attrs={'class': SELECT_CSS}),
            'arafat_details': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. AC Marquees with Buffet meals'}),
            'muzdalifah_details': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. Open air night stay with snack pack'}),
            'post_haj_days': forms.NumberInput(attrs={'class': INPUT_CSS, 'min': 0}),
            'rate_double_sharing': forms.NumberInput(attrs={'class': INPUT_CSS, 'step': '0.01'}),
            'rate_triple_sharing': forms.NumberInput(attrs={'class': INPUT_CSS, 'step': '0.01'}),
            'rate_quad_sharing': forms.NumberInput(attrs={'class': INPUT_CSS, 'step': '0.01'}),
            'is_active': forms.CheckboxInput(attrs={'class': CHECKBOX_CSS}),
        }


class PilgrimForm(forms.ModelForm):
    class Meta:
        model = Pilgrim
        fields = [
            'account', 'cohort', 'package', 'sub_fund', 'sharing_type',
            'family_members_count', 'total_package_cost', 'employee_no', 'name_and_designation',
            'cnic', 'passport_number', 'city', 'unit_or_formation', 'contact_number', 'is_active'
        ]
        widgets = {
            'account': forms.Select(attrs={'class': SELECT_CSS}),
            'cohort': forms.Select(attrs={'class': SELECT_CSS, 'id': 'id_cohort'}),
            'package': forms.Select(attrs={'class': SELECT_CSS, 'id': 'id_package'}),
            'sub_fund': forms.Select(attrs={'class': SELECT_CSS}),
            'sharing_type': forms.Select(attrs={'class': SELECT_CSS, 'id': 'id_sharing_type'}),
            'family_members_count': forms.NumberInput(attrs={'class': INPUT_CSS, 'min': 1, 'id': 'id_family_members_count'}),
            'total_package_cost': forms.NumberInput(attrs={'class': INPUT_CSS, 'step': '0.01', 'id': 'id_total_package_cost'}),
            'employee_no': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. EMP-12345'}),
            'name_and_designation': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. Muhammad Ali (Accountant)'}),
            'cnic': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. 37405-1234567-1'}),
            'passport_number': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'Optional passport number'}),
            'city': forms.Select(attrs={'class': SELECT_CSS}),
            'unit_or_formation': forms.Select(attrs={'class': SELECT_CSS}),
            'contact_number': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. 0300-1234567'}),
            'is_active': forms.CheckboxInput(attrs={'class': CHECKBOX_CSS}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'package' in self.fields:
            self.fields['package'].required = False
            self.fields['package'].queryset = CohortPackage.objects.filter(is_active=True)
            if self.instance and getattr(self.instance, 'cohort_id', None):
                self.fields['package'].queryset = CohortPackage.objects.filter(cohort_id=self.instance.cohort_id, is_active=True)
        if 'total_package_cost' in self.fields:
            self.fields['total_package_cost'].required = False

    def clean(self):
        cleaned_data = super().clean()
        package = cleaned_data.get('package')
        sharing_type = cleaned_data.get('sharing_type')
        members = cleaned_data.get('family_members_count') or 1
        total_cost = cleaned_data.get('total_package_cost')
        if package and (not total_cost or total_cost == 0):
            rate = Decimal('0.00')
            if sharing_type == Pilgrim.SharingType.DOUBLE:
                rate = package.rate_double_sharing
            elif sharing_type == Pilgrim.SharingType.TRIPLE:
                rate = package.rate_triple_sharing
            elif sharing_type == Pilgrim.SharingType.QUAD:
                rate = package.rate_quad_sharing
            cleaned_data['total_package_cost'] = rate * Decimal(str(members))
        return cleaned_data


class TourOperatorForm(forms.ModelForm):
    class Meta:
        model = TourOperator
        fields = ['account', 'name', 'registration_number', 'city', 'focal_person', 'contact_number', 'bank_iban', 'is_active']
        widgets = {
            'account': forms.Select(attrs={'class': SELECT_CSS}),
            'name': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. Al-Haramain Travel & Tours'}),
            'registration_number': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. DTS / MoRA License No'}),
            'city': forms.Select(attrs={'class': SELECT_CSS}),
            'focal_person': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'Contact person name'}),
            'contact_number': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'Phone number'}),
            'bank_iban': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. PK36MEZN0001234567890101'}),
            'is_active': forms.CheckboxInput(attrs={'class': CHECKBOX_CSS}),
        }
