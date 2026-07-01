from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0005_merge_20260630_0938"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="joblog",
            index=models.Index(fields=["project", "id"], name="joblog_project_id_idx"),
        ),
    ]
