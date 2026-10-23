from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0019_add_approved_inflow_amount'),
    ]

    operations = [
        migrations.CreateModel(
            name='BudgetInflowLine',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=18)),
                ('remarks', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('account_head', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='inflow_budget_lines', to='core.accounthead')),
                ('budget', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='inflow_lines', to='core.budget')),
                ('budget_type', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='inflow_budget_lines', to='core.budgettype')),
                ('unit', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='inflow_budget_lines', to='core.unit')),
            ],
            options={
                'verbose_name': 'Inflow Budget Line',
                'verbose_name_plural': 'Inflow Budget Lines',
                'ordering': ['budget', 'account_head'],
            },
        ),
        migrations.AddConstraint(
            model_name='budgetinflowline',
            constraint=models.UniqueConstraint(fields=('budget', 'account_head', 'budget_type', 'unit'), name='unique_inflow_budget_line_with_unit'),
        ),
        migrations.AddConstraint(
            model_name='budgetinflowline',
            constraint=models.UniqueConstraint(condition=models.Q(('unit__isnull', True)), fields=('budget', 'account_head', 'budget_type'), name='unique_inflow_budget_line_without_unit'),
        ),
    ]
