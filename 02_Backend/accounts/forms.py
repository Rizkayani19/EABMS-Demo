from django import forms
from django.contrib.auth.forms import SetPasswordForm, UserChangeForm, UserCreationForm
from django.contrib.auth.models import User

from core.models import Account, UserProfile


TEXT_CLASS = 'w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300'
CHECKBOX_CLASS = 'h-4 w-4 rounded border-slate-300 text-emerald-600'


class AdminUserCreationForm(UserCreationForm):
    role = forms.ChoiceField(choices=UserProfile.Role.choices)
    default_account = forms.ModelChoiceField(
        queryset=Account.objects.filter(is_active=True).order_by('display_order', 'name'),
        required=False,
        empty_label='No default account',
    )
    is_active = forms.BooleanField(required=False, initial=True)

    class Meta:
        model = User
        fields = (
            'username', 'first_name', 'last_name', 'email', 'role',
            'default_account', 'is_active', 'password1', 'password2',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', TEXT_CLASS)
        self.fields['is_active'].widget.attrs.update({'class': CHECKBOX_CLASS})

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_staff = False
        user.is_superuser = False
        user.is_active = self.cleaned_data.get('is_active', True)
        if commit:
            user.save()
        return user


class AdminUserUpdateForm(UserChangeForm):
    password = None
    role = forms.ChoiceField(choices=UserProfile.Role.choices)
    default_account = forms.ModelChoiceField(
        queryset=Account.objects.filter(is_active=True).order_by('display_order', 'name'),
        required=False,
        empty_label='No default account',
    )
    is_active = forms.BooleanField(required=False)

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'role', 'default_account', 'is_active')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        profile, _ = UserProfile.objects.get_or_create(user=self.instance)
        self.fields['username'].disabled = True
        self.fields['role'].initial = profile.role
        self.fields['default_account'].initial = profile.default_account_id
        self.fields['is_active'].initial = bool(self.instance.is_active and profile.is_active)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', TEXT_CLASS)
        self.fields['is_active'].widget.attrs.update({'class': CHECKBOX_CLASS})

    def clean_username(self):
        return self.instance.username


class AdminPasswordResetForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', TEXT_CLASS)
