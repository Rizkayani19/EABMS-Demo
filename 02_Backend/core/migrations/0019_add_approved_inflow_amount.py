from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0018_import_source_hash_unique"),
    ]

    operations = [
        migrations.AddField(
            model_name="futurebudgetline",
            name="approved_inflow_amount",
            field=models.DecimalField(
                decimal_places=2,
                max_digits=14,
                null=True,
                blank=True,
            ),
        ),
    ]
