from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Transaction, Reimbursement, Account, MajorHead, AccountHead, SubHead, Unit, InternalSection


class BaseTransactionForm(forms.ModelForm):
    document = forms.FileField(required=False, help_text="Optional supporting document")

    class Meta:
        model = Transaction
        fields = '__all__'

    def __init__(self, *args, financial_year=None, account=None, **kwargs):
        self.account = account
        super().__init__(*args, **kwargs)
        self.financial_year = financial_year
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control w-full p-2 border rounded'
        if 'amount' in self.fields:
            self.fields['amount'].widget.attrs['min'] = '0.01'
            self.fields['amount'].widget.attrs['step'] = '0.01'
        if 'transaction_date' in self.fields:
            self.fields['transaction_date'].widget.input_type = 'date'
            if self.financial_year:
                self.fields['transaction_date'].widget.attrs['min'] = self.financial_year.start_date.isoformat()
                self.fields['transaction_date'].widget.attrs['max'] = self.financial_year.end_date.isoformat()
        if 'transaction_units' in self.fields:
            self.fields['transaction_units'].queryset = Unit.objects.filter(is_active=True).order_by('display_order', 'name')
            self.fields['transaction_units'].required = False
            self.fields['transaction_units'].label = 'Units / Organisations'
            self.fields['transaction_units'].widget = forms.CheckboxSelectMultiple(
                choices=self.fields['transaction_units'].choices
            )
        if 'transaction_sections' in self.fields:
            self.fields['transaction_sections'].queryset = InternalSection.objects.filter(is_active=True).order_by('display_order', 'name')
            self.fields['transaction_sections'].required = False
            self.fields['transaction_sections'].label = 'Internal Sections'
            self.fields['transaction_sections'].widget = forms.CheckboxSelectMultiple(
                choices=self.fields['transaction_sections'].choices
            )
        if 'internal_section' in self.fields:
            self.fields['internal_section'].queryset = InternalSection.objects.filter(is_active=True).order_by('display_order', 'name')
            self.fields['internal_section'].required = False
        if 'unit' in self.fields:
            self.fields['unit'].queryset = Unit.objects.filter(is_active=True).order_by('display_order', 'name')
            self.fields['unit'].required = False
        if 'pass_through' in self.fields:
            self.fields['pass_through'].required = False
            self.fields['pass_through'].label = 'Pass-through'
        if 'payee_or_source' in self.fields:
            self.fields['payee_or_source'].widget = forms.TextInput(attrs={
                'class': 'form-control w-full p-2 border rounded',
                'placeholder': 'Enter remitter / source party or beneficiary'
            })
        if 'reference' in self.fields:
            self.fields['reference'].widget = forms.TextInput(attrs={
                'class': 'form-control w-full p-2 border rounded',
                'placeholder': 'e.g. Cheque #, Sanction letter ID'
            })

        self._configure_operational_attribution()

    def _configure_operational_attribution(self):
        """Show only operational attribution appropriate to the active fund."""

        fields = [
            'cohort',
            'package',
            'pilgrim',
            'tour_operator',
            'ceremony_event',
            'ceremony_venue',
        ]

        # Preserve compatibility with existing tests/forms which don't
        # provide an account.
        if not self.account:
            return

        code = (getattr(self.account, 'code', '') or '').upper()

        if code == 'CPF':
            allowed = {
                'cohort',
                'package',
                'pilgrim',
                'tour_operator',
            }
        elif code == 'EWF':
            allowed = {
                'ceremony_event',
                'ceremony_venue',
            }
        else:
            allowed = set()

        for name in fields:
            if name in self.fields and name not in allowed:
                self.fields.pop(name)

        if not allowed:
            return

        from masters.models import (
            Cohort,
            CohortPackage,
            Pilgrim,
            TourOperator,
            CeremonyEvent,
            CeremonyVenue,
        )

        if 'cohort' in self.fields:
            self.fields['cohort'].queryset = (
                Cohort.objects
                .filter(account=self.account, is_active=True)
                .order_by('start_date', 'code')
            )
            self.fields['cohort'].required = False

        if 'package' in self.fields:
            qs = (
                CohortPackage.objects
                .filter(
                    cohort__account=self.account,
                    is_active=True,
                )
                .select_related('cohort')
                .order_by('cohort__start_date', 'package_code')
            )

            selected = None

            if self.is_bound:
                selected = self.data.get(
                    self.add_prefix('cohort')
                )

            if not selected:
                selected = getattr(
                    self.instance,
                    'cohort_id',
                    None,
                )

            if selected:
                qs = qs.filter(cohort_id=selected)
            else:
                qs = CohortPackage.objects.none()

            self.fields['package'].queryset = qs
            self.fields['package'].required = False

        if 'pilgrim' in self.fields:
            self.fields['pilgrim'].queryset = (
                Pilgrim.objects
                .filter(account=self.account, is_active=True)
                .select_related('cohort', 'package')
                .order_by('employee_no', 'name_and_designation')
            )
            self.fields['pilgrim'].required = False

        if 'tour_operator' in self.fields:
            self.fields['tour_operator'].queryset = (
                TourOperator.objects
                .filter(account=self.account, is_active=True)
                .order_by('name')
            )
            self.fields['tour_operator'].required = False

        if 'ceremony_event' in self.fields:
            self.fields['ceremony_event'].queryset = (
                CeremonyEvent.objects
                .filter(is_active=True)
                .order_by('name')
            )
            self.fields['ceremony_event'].required = False

        if 'ceremony_venue' in self.fields:
            self.fields['ceremony_venue'].queryset = (
                CeremonyVenue.objects
                .filter(is_active=True)
                .order_by('name')
            )
            self.fields['ceremony_venue'].required = False

        labels = {
            'cohort': 'Cohort',
            'package': 'Package',
            'pilgrim': 'Pilgrim',
            'tour_operator': 'Tour Operator',
            'ceremony_event': 'Ceremony Event',
            'ceremony_venue': 'Ceremony Venue',
        }

        for name, label in labels.items():
            if name in self.fields:
                self.fields[name].label = label

    def save(self, commit=True):
        instance = super().save(commit=False)
        selected_units = self.cleaned_data.get('transaction_units')
        if selected_units and not instance.unit:
            instance.unit = selected_units.first() if hasattr(selected_units, 'first') else selected_units[0]
        selected_sections = self.cleaned_data.get('transaction_sections')
        if selected_sections and not instance.internal_section:
            instance.internal_section = selected_sections.first() if hasattr(selected_sections, 'first') else selected_sections[0]
        if commit:
            instance.save()
            self.save_m2m()
        return instance

    def clean_transaction_date(self):
        transaction_date = self.cleaned_data.get('transaction_date')
        if transaction_date and self.financial_year:
            if not (self.financial_year.start_date <= transaction_date <= self.financial_year.end_date):
                raise ValidationError(
                    f"Transaction date {transaction_date:%d-%b-%Y} is outside the selected "
                    f"Financial Year ({self.financial_year.code}). Enter a date between "
                    f"{self.financial_year.start_date:%d-%b-%Y} and "
                    f"{self.financial_year.end_date:%d-%b-%Y}."
                )
        return transaction_date

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is None or amount <= 0:
            raise ValidationError("Transaction amount must be strictly positive.")
        return amount

    def clean_account_head(self):
        account_head = self.cleaned_data.get('account_head')
        if not account_head:
            raise ValidationError("Please select an Account Head.")
        if not account_head.is_active:
            raise ValidationError("Inactive Master cannot be used.")
        return account_head

    def clean_major_head(self):
        major_head = self.cleaned_data.get('major_head')
        account_head = self.cleaned_data.get('account_head')
        if not major_head and account_head and account_head.major_head:
            major_head = account_head.major_head
        if not major_head:
            raise ValidationError("Please select a Sub Fund.")
        return major_head


class InflowForm(BaseTransactionForm):
    class Meta:
        model = Transaction
        fields = [
            'transaction_date', 'major_head', 'account_head', 'sub_head', 'amount',
            'inflow_type', 'payee_or_source', 'reference', 'description',
            'pass_through', 'transaction_units', 'transaction_sections',
            'cohort', 'package', 'pilgrim', 'tour_operator',
            'ceremony_event', 'ceremony_venue', 'remarks'
        ]
        labels = {
            'transaction_date': 'Date',
            'major_head': 'Sub Fund',
            'account_head': 'Account Head',
            'sub_head': 'Sub Head',
            'payee_or_source': 'Source',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'major_head' in self.fields:
            mh_qs = MajorHead.objects.filter(is_active=True)
            if self.account:
                mh_qs = mh_qs.filter(account=self.account)
            self.fields['major_head'].queryset = mh_qs
            self.fields['major_head'].required = True
            self.fields['major_head'].label = 'Sub Fund (Tier 1)'
            self.fields['major_head'].widget.attrs.update({
                'hx-get': '/transactions/ajax/load-account-heads/?direction=INFLOW',
                'hx-target': '#id_account_head',
            })
        qs = AccountHead.objects.filter(
            is_active=True,
            head_type__in=[AccountHead.HeadType.INFLOW, AccountHead.HeadType.BOTH],
        )
        if self.account:
            qs = qs.filter(account=self.account)
        self.fields['account_head'].queryset = qs
        self.fields['account_head'].required = True
        self.fields['account_head'].label = 'Account Head (Tier 2)'
        self.fields['account_head'].widget.attrs.update({
            'hx-get': '/transactions/ajax/load-sub-heads/',
            'hx-target': '#id_sub_head',
        })
        self.fields['sub_head'].required = False
        self.fields['sub_head'].label = 'Sub Head (Tier 3)'
        if 'description' in self.fields:
            self.fields['description'].required = True

    def clean(self):
        cleaned_data = super().clean()
        account_head = cleaned_data.get('account_head')
        major_head = cleaned_data.get('major_head')
        if not major_head and account_head and account_head.major_head:
            cleaned_data['major_head'] = account_head.major_head
            self.cleaned_data['major_head'] = account_head.major_head
        sub_head = cleaned_data.get('sub_head')
        if sub_head and not sub_head.is_active:
            raise ValidationError({'sub_head': 'Inactive Master cannot be used.'})
        return cleaned_data


class OutflowForm(BaseTransactionForm):
    class Meta:
        model = Transaction
        fields = [
            'transaction_date', 'major_head', 'account_head', 'sub_head', 'amount',
            'outflow_nature', 'payee_or_source', 'purpose', 'reference',
            'pass_through', 'transaction_units', 'transaction_sections',
            'cohort', 'package', 'pilgrim', 'tour_operator',
            'ceremony_event', 'ceremony_venue', 'remarks'
        ]
        labels = {
            'transaction_date': 'Date',
            'major_head': 'Sub Fund',
            'account_head': 'Account Head',
            'sub_head': 'Sub Head',
            'payee_or_source': 'Payee',
            'purpose': 'Purpose/Description',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'major_head' in self.fields:
            mh_qs = MajorHead.objects.filter(is_active=True)
            if self.account:
                mh_qs = mh_qs.filter(account=self.account)
            self.fields['major_head'].queryset = mh_qs
            self.fields['major_head'].required = True
            self.fields['major_head'].label = 'Sub Fund (Tier 1)'
            self.fields['major_head'].widget.attrs.update({
                'hx-get': '/transactions/ajax/load-account-heads/?direction=OUTFLOW',
                'hx-target': '#id_account_head',
            })
        qs = AccountHead.objects.filter(
            is_active=True,
            head_type__in=[AccountHead.HeadType.OUTFLOW, AccountHead.HeadType.BOTH],
        )
        if self.account:
            qs = qs.filter(account=self.account)
        self.fields['account_head'].queryset = qs
        self.fields['account_head'].required = True
        self.fields['account_head'].label = 'Account Head (Tier 2)'
        self.fields['account_head'].widget.attrs.update({
            'hx-get': '/transactions/ajax/load-sub-heads/',
            'hx-target': '#id_sub_head',
        })
        self.fields['sub_head'].required = False
        self.fields['sub_head'].label = 'Sub Head (Tier 3)'
        if 'purpose' in self.fields:
            self.fields['purpose'].required = True

    def clean(self):
        cleaned_data = super().clean()
        account_head = cleaned_data.get('account_head')
        major_head = cleaned_data.get('major_head')
        if not major_head and account_head and account_head.major_head:
            cleaned_data['major_head'] = account_head.major_head
            self.cleaned_data['major_head'] = account_head.major_head
        sub_head = cleaned_data.get('sub_head')
        if sub_head and not sub_head.is_active:
            raise ValidationError({'sub_head': 'Inactive Master cannot be used.'})
        return cleaned_data


class ReimbursementForm(forms.ModelForm):
    document = forms.FileField(required=False, help_text="Optional supporting document")

    class Meta:
        model = Reimbursement
        fields = ['reimbursement_type', 'expected_amount', 'expected_date', 'source', 'reference', 'status', 'remarks']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control w-full p-2 border rounded'
        if 'expected_date' in self.fields:
            self.fields['expected_date'].widget.input_type = 'date'


class InternalTransferForm(forms.Form):
    transaction_date = forms.DateField(
        label="Transfer Date",
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control w-full p-2 border rounded font-semibold text-slate-800'
        })
    )

    # Source (Debit / From)
    source_major_head = forms.ModelChoiceField(
        queryset=MajorHead.objects.none(),
        label="Source Sub-Fund (Tier 1)",
        widget=forms.Select(attrs={
            'class': 'form-control w-full p-2 border rounded font-semibold text-slate-800',
            'hx-get': '/transactions/ajax/load-account-heads/',
            'hx-target': '#id_source_account_head',
        })
    )
    source_account_head = forms.ModelChoiceField(
        queryset=AccountHead.objects.none(),
        label="Source Account Head (Tier 2)",
        widget=forms.Select(attrs={
            'class': 'form-control w-full p-2 border rounded font-semibold text-slate-800',
            'hx-get': '/transactions/ajax/load-sub-heads/',
            'hx-target': '#id_source_sub_head',
        })
    )
    source_sub_head = forms.ModelChoiceField(
        queryset=SubHead.objects.none(),
        required=False,
        label="Source Sub Head (Tier 3, Optional)",
        widget=forms.Select(attrs={
            'class': 'form-control w-full p-2 border rounded font-semibold text-slate-800',
        })
    )

    # Destination (Credit / To)
    dest_major_head = forms.ModelChoiceField(
        queryset=MajorHead.objects.none(),
        label="Destination Sub-Fund (Tier 1)",
        widget=forms.Select(attrs={
            'class': 'form-control w-full p-2 border rounded font-semibold text-slate-800',
            'hx-get': '/transactions/ajax/load-account-heads/',
            'hx-target': '#id_dest_account_head',
        })
    )
    dest_account_head = forms.ModelChoiceField(
        queryset=AccountHead.objects.none(),
        label="Destination Account Head (Tier 2)",
        widget=forms.Select(attrs={
            'class': 'form-control w-full p-2 border rounded font-semibold text-slate-800',
            'hx-get': '/transactions/ajax/load-sub-heads/',
            'hx-target': '#id_dest_sub_head',
        })
    )
    dest_sub_head = forms.ModelChoiceField(
        queryset=SubHead.objects.none(),
        required=False,
        label="Destination Sub Head (Tier 3, Optional)",
        widget=forms.Select(attrs={
            'class': 'form-control w-full p-2 border rounded font-semibold text-slate-800',
        })
    )

    # Financial & Authority Details
    amount = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal('0.01'),
        label="Transfer Amount (PKR)",
        widget=forms.NumberInput(attrs={
            'placeholder': '0.00',
            'step': '0.01',
            'class': 'form-control w-full p-2 border rounded font-mono font-bold text-slate-900 text-lg'
        })
    )
    sanction_reference = forms.CharField(
        max_length=255,
        required=True,
        label="Sanction / Authority Reference",
        widget=forms.TextInput(attrs={
            'placeholder': 'e.g. Board approval ref. BRD/2026/014',
            'class': 'form-control w-full p-2 border rounded font-medium'
        })
    )
    description = forms.CharField(
        required=False,
        label="Transfer Remarks / Rationale",
        widget=forms.Textarea(attrs={
            'rows': 2,
            'placeholder': 'State the operational reason for internal transfer / adjustment...',
            'class': 'form-control w-full p-2 border rounded font-medium'
        })
    )

    def __init__(self, *args, account=None, financial_year=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.account = account
        self.financial_year = financial_year

        if not self.initial.get('transaction_date'):
            self.initial['transaction_date'] = timezone.now().date()

        if self.financial_year and 'transaction_date' in self.fields:
            self.fields['transaction_date'].widget.attrs['min'] = self.financial_year.start_date.isoformat()
            self.fields['transaction_date'].widget.attrs['max'] = self.financial_year.end_date.isoformat()

        if account:
            mh_qs = MajorHead.objects.filter(account=account, is_active=True).order_by('display_order', 'name')
            ah_qs = AccountHead.objects.filter(account=account, is_active=True).order_by('display_order', 'name')
            sh_qs = SubHead.objects.filter(account=account, is_active=True).order_by('display_order', 'name')

            self.fields['source_major_head'].queryset = mh_qs
            self.fields['dest_major_head'].queryset = mh_qs
            self.fields['source_account_head'].queryset = ah_qs
            self.fields['dest_account_head'].queryset = ah_qs
            self.fields['source_sub_head'].queryset = sh_qs
            self.fields['dest_sub_head'].queryset = sh_qs

            src_mh_id = self.initial.get('source_major_head') or (self.data.get('source_major_head') if hasattr(self, 'data') and self.data else None)
            if src_mh_id:
                src_ahs = AccountHead.objects.filter(account=account, major_head_id=src_mh_id, is_active=True).order_by('display_order', 'name')
                if src_ahs.exists():
                    self.fields['source_account_head'].queryset = src_ahs
                    if not self.initial.get('source_account_head'):
                        self.initial['source_account_head'] = src_ahs.first().id

            dst_mh_id = self.initial.get('dest_major_head') or (self.data.get('dest_major_head') if hasattr(self, 'data') and self.data else None)
            if dst_mh_id:
                dst_ahs = AccountHead.objects.filter(account=account, major_head_id=dst_mh_id, is_active=True).order_by('display_order', 'name')
                if dst_ahs.exists():
                    self.fields['dest_account_head'].queryset = dst_ahs
                    if not self.initial.get('dest_account_head'):
                        self.initial['dest_account_head'] = dst_ahs.first().id

    def clean(self):
        cleaned_data = super().clean()
        t_date = cleaned_data.get('transaction_date')
        if t_date and self.financial_year:
            if t_date < self.financial_year.start_date or t_date > self.financial_year.end_date:
                self.add_error(
                    'transaction_date',
                    f"Transfer date must be within {self.financial_year.name} "
                    f"({self.financial_year.start_date.strftime('%d-%m-%Y')} to {self.financial_year.end_date.strftime('%d-%m-%Y')})."
                )

        src_ah = cleaned_data.get('source_account_head')
        dst_ah = cleaned_data.get('dest_account_head')
        src_sh = cleaned_data.get('source_sub_head')
        dst_sh = cleaned_data.get('dest_sub_head')

        if src_ah and dst_ah and src_ah == dst_ah:
            if src_sh == dst_sh:
                raise ValidationError("Source and Destination cannot be the exact same Account Head / Sub Head.")
        return cleaned_data
