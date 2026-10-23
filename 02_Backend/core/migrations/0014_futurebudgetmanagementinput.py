from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0013_historicalbudgetallocation'),
    ]

    operations = [
        migrations.CreateModel(
            name='FutureBudgetManagementInput',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('input_type', models.CharField(choices=[('CONTINUING', 'Continuing Requirement'), ('ADDITIONAL', 'Additional Requirement'), ('OTHER', 'Other Management Input')], max_length=20)),
                ('description', models.CharField(max_length=300)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=18)),
                ('justification', models.TextField()),
                ('reference', models.CharField(blank=True, max_length=255)),
                ('effective_date', models.DateField(blank=True, null=True)),
                ('end_date', models.DateField(blank=True, null=True)),
                ('status', models.CharField(choices=[('DRAFT', 'Draft'), ('ACTIVE', 'Active'), ('REJECTED', 'Rejected'), ('CLOSED', 'Closed')], db_index=True, default='DRAFT', max_length=20)),
                ('remarks', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('account_head', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='future_budget_management_inputs', to='core.accounthead')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='future_budget_management_inputs_created', to=settings.AUTH_USER_MODEL)),
                ('future_budget', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='management_inputs', to='core.futurebudget')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='future_budget_management_inputs_updated', to=settings.AUTH_USER_MODEL)),
                ('internal_sections', models.ManyToManyField(blank=True, related_name='future_budget_management_inputs', to='core.internalsection')),
                ('units', models.ManyToManyField(blank=True, related_name='future_budget_management_inputs', to='core.unit')),
            ],
            options={
                'ordering': ['input_type', 'account_head__name', '-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='futurebudgetmanagementinput',
            index=models.Index(fields=['future_budget', 'input_type', 'status'], name='core_future_futurebu_1b5d20_idx'),
        ),
        migrations.AddIndex(
            model_name='futurebudgetmanagementinput',
            index=models.Index(fields=['future_budget', 'account_head', 'status'], name='core_future_futurebu_2d1a95_idx'),
        ),
    ]
