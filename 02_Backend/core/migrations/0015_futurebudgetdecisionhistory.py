from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0014_futurebudgetmanagementinput"),
    ]

    operations = [
        migrations.CreateModel(
            name="FutureBudgetDecisionHistory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(choices=[("PROPOSE", "Proposed"), ("APPROVE", "Approved"), ("REJECT", "Proposal Rejected"), ("REOPEN", "Approval Reopened")], db_index=True, max_length=20)),
                ("previous_proposed", models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True)),
                ("new_proposed", models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True)),
                ("previous_approved", models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True)),
                ("new_approved", models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True)),
                ("system_suggested_snapshot", models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True)),
                ("reason", models.TextField(blank=True)),
                ("remarks", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="future_budget_decision_history", to=settings.AUTH_USER_MODEL)),
                ("future_budget_line", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="decision_history", to="core.futurebudgetline")),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="futurebudgetdecisionhistory",
            index=models.Index(fields=["future_budget_line", "created_at"], name="core_future_line_hist_1a2b3c"),
        ),
        migrations.AddIndex(
            model_name="futurebudgetdecisionhistory",
            index=models.Index(fields=["future_budget_line", "action", "created_at"], name="core_future_line_hist_4d5e6f"),
        ),
    ]
