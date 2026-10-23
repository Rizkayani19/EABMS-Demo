from django.db import migrations, models
import django.db.models.deletion


SECTIONS = [
    ('FIN', 'Finance', "Accounts, budgeting and financial reporting.", 10),
    ('HR', 'HR & Personnel', "Recruitment, leave, discipline and personnel records.", 20),
    ('EVT', 'Events', "Corporate events, award ceremonies and the training academy.", 30),
    ('TRV', 'Travel Programmes', "Employee Hajj/Umrah travel programmes and related administration.", 40),
    ('ADM', 'Administration', "Administration, facilities, travel approvals and long-service recognition.", 50),
    ('POL', 'Policy', "Plans, policies, staff handbook and corporate publications.", 60),
    ('COORD', 'Coordination', "Coordination across departments, executive programmes, administration and security liaison.", 70),
    ('SEC', 'Security', "Corporate Security — premises security and related matters.", 80),
    ('WELFARE', 'Employee Welfare', "Employee welfare, family support and benefits.", 90),
    ('RSK', 'Risk & Compliance', "Risk, compliance and cyber security.", 100),
    ('DMC', 'IT Services', 'IT matters including computers, hardware, application development and related digital/technical support.', 110),
]

UNITS = [
    ('BR-NORTH', 'Northern Branch'),
    ('BR-SOUTH', 'Southern Branch'),
    ('ACAD', 'Training Academy'),
    ('HQO', 'Regional HQ'),
    ('BR-EAST', 'Eastern Branch'),
    ('BR-TRG', 'Training Centre'),
]

RESPONSIBILITIES = [
    ('ACAD', 'EVT', True, 'ACAD-related affairs are managed by EVT.'),
    ('BR-SOUTH', 'SEC', True, 'Southern Branch security affairs are managed by Corporate Security.'),
]


def seed_organisational_masters(apps, schema_editor):
    InternalSection = apps.get_model('masters', 'InternalSection')
    Unit = apps.get_model('core', 'Unit')
    Responsibility = apps.get_model('masters', 'UnitSectionResponsibility')

    sections = {}
    for code, name, description, order in SECTIONS:
        obj, _ = InternalSection.objects.update_or_create(
            code=code,
            defaults={
                'name': name,
                'description': description,
                'is_active': True,
                'display_order': order,
            },
        )
        sections[code] = obj

    units = {}
    for code, name in UNITS:
        obj, _ = Unit.objects.get_or_create(
            code=code,
            defaults={'name': name, 'is_active': True},
        )
        units[code] = obj

    for unit_code, section_code, primary, notes in RESPONSIBILITIES:
        Responsibility.objects.update_or_create(
            unit=units[unit_code],
            section=sections[section_code],
            defaults={'is_primary': primary, 'is_active': True, 'notes': notes},
        )


def unseed_organisational_masters(apps, schema_editor):
    # Preserve master data on rollback; operational installations may have edited it.
    pass


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('core', '0010_alter_transaction_document_reference_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='InternalSection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(db_index=True, max_length=50, unique=True)),
                ('name', models.CharField(max_length=100, unique=True)),
                ('description', models.TextField(blank=True)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('display_order', models.PositiveIntegerField(default=1)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Internal Section',
                'verbose_name_plural': 'Internal Sections',
                'ordering': ['display_order', 'name'],
            },
        ),
        migrations.CreateModel(
            name='UnitSectionResponsibility',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_primary', models.BooleanField(default=False, help_text='Marks the normal/primary responsible section where one exists.')),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('section', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='unit_responsibilities', to='masters.internalsection')),
                ('unit', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='section_responsibilities', to='core.unit')),
            ],
            options={
                'verbose_name': 'Unit / Section Responsibility',
                'verbose_name_plural': 'Unit / Section Responsibilities',
                'ordering': ['unit__display_order', 'section__display_order', 'unit__name', 'section__name'],
            },
        ),
        migrations.AddConstraint(
            model_name='unitsectionresponsibility',
            constraint=models.UniqueConstraint(fields=('unit', 'section'), name='unique_unit_section_responsibility'),
        ),
        migrations.RunPython(seed_organisational_masters, unseed_organisational_masters),
    ]
