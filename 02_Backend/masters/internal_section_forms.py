from django import forms
from core.models import InternalSection

INPUT_CSS = "w-full px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 text-sm"
TEXTAREA_CSS = "w-full px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 text-sm"
CHECKBOX_CSS = "h-4 w-4 text-emerald-600 focus:ring-emerald-500 border-slate-300 rounded"


class InternalSectionForm(forms.ModelForm):
    class Meta:
        model = InternalSection
        fields = ['code', 'name', 'description', 'display_order', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. EVT'}),
            'name': forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': 'e.g. EVT'}),
            'description': forms.Textarea(attrs={'class': TEXTAREA_CSS, 'rows': 5}),
            'display_order': forms.NumberInput(attrs={'class': INPUT_CSS, 'min': 1}),
            'is_active': forms.CheckboxInput(attrs={'class': CHECKBOX_CSS}),
        }
