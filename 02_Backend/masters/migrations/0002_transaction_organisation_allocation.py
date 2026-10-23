from django.db import migrations, models
import django.db.models.deletion


def seed_legacy_unit_allocations(apps, schema_editor):
    """Preserve existing Transaction.unit attribution at allocation grain."""
    Transaction = apps.get_model('core', 'Transaction')
    Allocation = apps.get_model('masters', 'TransactionOrganisationAllocation')
    rows = []
    for tx in Transaction.objects.exclude(unit_id__isnull=True).iterator():
        rows.append(Allocation(
            transaction_id=tx.pk,
            unit_id=tx.unit_id,
            internal_section_id=None,
            allocated_amount=tx.amount,
            notes='Migrated from legacy Transaction.unit attribution during Gate N3.',
        ))
        if len(rows) >= 1000:
            Allocation.objects.bulk_create(rows, ignore_conflicts=True)
            rows = []
    if rows:
        Allocation.objects.bulk_create(rows, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0010_alter_transaction_document_reference_and_more'),
        ('masters', '0001_internal_section_and_unit_responsibility'),
    ]

    operations = [
        migrations.CreateModel(
            name='TransactionOrganisationAllocation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('allocated_amount', models.DecimalField(decimal_places=2, max_digits=18)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('internal_section', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='transaction_organisation_allocations', to='masters.internalsection')),
                ('transaction', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='organisation_allocations', to='core.transaction')),
                ('unit', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='transaction_organisation_allocations', to='core.unit')),
            ],
            options={
                'verbose_name': 'Transaction Organisation Allocation',
                'verbose_name_plural': 'Transaction Organisation Allocations',
                'ordering': ['transaction__transaction_date', 'transaction', 'unit', 'internal_section'],
            },
        ),
        migrations.AddConstraint(
            model_name='transactionorganisationallocation',
            constraint=models.CheckConstraint(condition=models.Q(allocated_amount__gt=0), name='transaction_org_alloc_amount_positive'),
        ),
        migrations.AddConstraint(
            model_name='transactionorganisationallocation',
            constraint=models.CheckConstraint(condition=models.Q(unit__isnull=False) | models.Q(internal_section__isnull=False), name='transaction_org_alloc_has_dimension'),
        ),
        migrations.AddConstraint(
            model_name='transactionorganisationallocation',
            constraint=models.UniqueConstraint(fields=('transaction', 'unit', 'internal_section'), name='unique_transaction_org_allocation'),
        ),
        migrations.RunPython(seed_legacy_unit_allocations, migrations.RunPython.noop),
    ]
