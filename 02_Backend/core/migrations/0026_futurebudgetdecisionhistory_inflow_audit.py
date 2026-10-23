from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0025_alter_accounthead_unique_together"),
    ]

    operations = [
        migrations.AddField(
            model_name="futurebudgetdecisionhistory",
            name="previous_approved_inflow",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True),
        ),
        migrations.AddField(
            model_name="futurebudgetdecisionhistory",
            name="previous_proposed_inflow",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True),
        ),
        migrations.AddField(
            model_name="futurebudgetdecisionhistory",
            name="new_approved_inflow",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True),
        ),
        migrations.AddField(
            model_name="futurebudgetdecisionhistory",
            name="new_proposed_inflow",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True),
        ),
    ]
