from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0012_futurebudgetallocation'),
    ]

    operations = [
        migrations.CreateModel(
            name='HistoricalBudgetAllocation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('allocated_amount', models.DecimalField(decimal_places=2, max_digits=18)),
                ('remarks', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('budget_line', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='historical_allocations', to='core.budgetline')),
                ('internal_section', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='historical_budget_allocations', to='core.internalsection')),
                ('unit', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='historical_budget_allocations', to='core.unit')),
            ],
            options={
                'verbose_name': 'Historical Budget Allocation',
                'verbose_name_plural': 'Historical Budget Allocations',
                'ordering': ['unit__name', 'internal_section__name', 'id'],
            },
        ),
        migrations.AddConstraint(
            model_name='historicalbudgetallocation',
            constraint=models.UniqueConstraint(
                fields=('budget_line', 'unit', 'internal_section'),
                name='uniq_hist_budget_line_org_allocation',
            ),
        ),
    ]
