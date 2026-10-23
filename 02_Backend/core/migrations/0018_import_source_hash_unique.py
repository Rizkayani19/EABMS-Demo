from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0017_import_source_fingerprints"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="importbatch",
            constraint=models.UniqueConstraint(
                condition=~models.Q(source_hash=""),
                fields=("account", "source_hash"),
                name="unique_import_source_hash_per_account",
            ),
        ),
    ]
