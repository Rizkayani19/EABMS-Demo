from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_organisational_attribution'),
    ]

    operations = [
        migrations.CreateModel(
            name='FutureBudgetAllocation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('allocated_amount', models.DecimalField(decimal_places=2, max_digits=14)),
                ('justification', models.TextField(blank=True)),
                ('remarks', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='future_budget_allocations_created', to='auth.user')),
                ('future_budget_line', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='allocations', to='core.futurebudgetline')),
                ('internal_section', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='future_budget_allocations', to='core.internalsection')),
                ('unit', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='future_budget_allocations', to='core.unit')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='future_budget_allocations_updated', to='auth.user')),
            ],
            options={
                'verbose_name': 'Future Budget Allocation',
                'verbose_name_plural': 'Future Budget Allocations',
                'ordering': ['unit__name', 'internal_section__name', 'id'],
            },
        ),
        migrations.AddConstraint(
            model_name='futurebudgetallocation',
            constraint=models.UniqueConstraint(
                fields=('future_budget_line', 'unit', 'internal_section'),
                name='uniq_future_budget_line_org_allocation',
            ),
        ),
    ]
