from django.db import migrations, models
import django.db.models.deletion


def seed_organisation_masters(apps, schema_editor):
    InternalSection = apps.get_model('core', 'InternalSection')
    Unit = apps.get_model('core', 'Unit')

    sections = [
        ('FIN', 'Finance', "Accounts, budgeting and financial reporting."),
        ('HR', 'HR & Personnel', "Recruitment, leave, discipline and personnel records."),
        ('EVT', 'Events', "Corporate events, award ceremonies and the training academy."),
        ('TRV', 'Travel Programmes', "Employee Hajj/Umrah travel programmes and related administration."),
        ('ADM', 'Administration', "Administration, facilities, travel approvals and long-service recognition."),
        ('POL', 'Policy', "Plans, policies, staff handbook and corporate publications."),
        ('COORD', "Coordination", "Coordination across departments, executive programmes, administration and security liaison."),
        ('SEC', "Security", "Corporate Security — premises security and related matters."),
        ('WELFARE', "Employee Welfare", "Employee welfare, family support and benefits."),
        ('RSK', "Risk & Compliance", "Risk, compliance and cyber security."),
        ('DMC', "IT Services", "IT matters including computers, hardware, application development and related digital/technical support."),
    ]
    for order, (code, name, description) in enumerate(sections, start=1):
        InternalSection.objects.update_or_create(
            code=code,
            defaults={'name': name, 'description': description, 'display_order': order, 'is_active': True},
        )

    units = [
        ('BR-NORTH', 'Northern Branch'),
        ('BR-SOUTH', 'Southern Branch'),
        ('ACAD', 'Training Academy'),
        ('HQO', 'Regional HQ'),
        ('BR-EAST', 'Eastern Branch'),
        ('BR-TRG', 'Training Centre'),
    ]
    for order, (code, name) in enumerate(units, start=1):
        Unit.objects.update_or_create(
            code=code,
            defaults={'name': name, 'display_order': order, 'is_active': True},
        )

    # Approved operational relationships.
    evt = InternalSection.objects.get(code='EVT')
    hqpm = InternalSection.objects.get(code='SEC')
    Unit.objects.get(code='ACAD').managed_by_sections.add(evt)
    Unit.objects.get(code='BR-SOUTH').managed_by_sections.add(hqpm)


def migrate_existing_unit_attribution(apps, schema_editor):
    Transaction = apps.get_model('core', 'Transaction')
    Unit = apps.get_model('core', 'Unit')
    for tx in Transaction.objects.exclude(unit__isnull=True).iterator():
        tx.transaction_units.add(tx.unit_id)


class Migration(migrations.Migration):
    dependencies = [('core', '0010_alter_transaction_document_reference_and_more')]

    operations = [
        migrations.CreateModel(
            name='InternalSection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(db_index=True, max_length=50, unique=True)),
                ('name', models.CharField(max_length=120, unique=True)),
                ('description', models.TextField(blank=True)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('display_order', models.PositiveIntegerField(default=1)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['display_order', 'name'], 'verbose_name': 'Internal Section', 'verbose_name_plural': 'Internal Sections'},
        ),
        migrations.AddField(
            model_name='unit', name='managed_by_sections',
            field=models.ManyToManyField(blank=True, help_text='Optional responsible Internal Sections; a Unit may have multiple managing Sections.', related_name='managed_units', to='core.internalsection'),
        ),
        migrations.AddField(
            model_name='transaction', name='internal_section',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='primary_transactions', to='core.internalsection'),
        ),
        migrations.AddField(
            model_name='transaction', name='transaction_sections',
            field=models.ManyToManyField(blank=True, related_name='attributed_transactions', to='core.internalsection'),
        ),
        migrations.AddField(
            model_name='transaction', name='transaction_units',
            field=models.ManyToManyField(blank=True, related_name='attributed_transactions', to='core.unit'),
        ),
        migrations.AddField(model_name='transaction', name='deleted_by', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='soft_deleted_transactions', to='auth.user')),
        migrations.AddField(model_name='transaction', name='deleted_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='transaction', name='deletion_reason', field=models.TextField(blank=True)),
        migrations.AlterField(
            model_name='transaction', name='status',
            field=models.CharField(choices=[('DRAFT', 'Draft'), ('ACTIVE', 'Active'), ('CANCELLED', 'Cancelled'), ('SOFT_DELETED', 'Soft Deleted')], db_index=True, default='DRAFT', max_length=20),
        ),
        migrations.RunPython(migrate_existing_unit_attribution, migrations.RunPython.noop),
        migrations.RunPython(seed_organisation_masters, migrations.RunPython.noop),
    ]
