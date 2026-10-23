from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0016_reconcile_model_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="importbatch",
            name="source_hash",
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
        migrations.AddField(
            model_name="importedrecord",
            name="row_hash",
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
    ]
