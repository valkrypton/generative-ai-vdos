import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_add_user_api_key"),
        ("core", "0001_add_provider"),
        ("projects", "0006_joblog_project_id_index"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="llmmodel",
            name="unique_provider_capability_model",
        ),
        migrations.AddField(
            model_name="llmmodel",
            name="owner",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="custom_llm_models",
                to="accounts.userprofile",
            ),
        ),
        migrations.AddConstraint(
            model_name="llmmodel",
            constraint=models.UniqueConstraint(
                fields=("provider", "capability", "model_id", "owner"),
                name="unique_provider_capability_model_owner",
            ),
        ),
    ]
