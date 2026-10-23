from django.db import migrations, models
import django.db.models.deletion


def migrate_section_master_data(apps, schema_editor):
    CoreSection = apps.get_model('core', 'InternalSection')
    MasterSection = apps.get_model('masters', 'InternalSection')
    Responsibility = apps.get_model('masters', 'UnitSectionResponsibility')

    section_id_map = {}

    for old in MasterSection.objects.all().order_by('id'):
        core, _ = CoreSection.objects.update_or_create(
            code=old.code,
            defaults={
                'name': old.name,
                'description': old.description,
                'is_active': old.is_active,
                'display_order': old.display_order,
            },
        )
        section_id_map[old.id] = core.id

    for responsibility in Responsibility.objects.all().iterator():
        new_section_id = section_id_map.get(responsibility.section_id)
        if new_section_id:
            responsibility.section_id = new_section_id
            responsibility.save(update_fields=['section'])


def reverse_migration(apps, schema_editor):
    # Do not delete/recreate operational master data on rollback.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0011_organisational_attribution'),
        ('masters', '0002_transaction_organisation_allocation'),
    ]

    operations = [
        migrations.RunPython(migrate_section_master_data, reverse_migration),
        migrations.AlterField(
            model_name='transactionorganisationallocation',
            name='internal_section',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='transaction_organisation_allocations',
                to='core.internalsection',
            ),
        ),
        migrations.AlterField(
            model_name='unitsectionresponsibility',
            name='section',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='unit_responsibilities',
                to='core.internalsection',
            ),
        ),
        migrations.DeleteModel(
            name='InternalSection',
        ),
    ]
