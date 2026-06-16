import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0001_initial"),
    ]

    operations = [
        # Scene — add both (neither existed)
        migrations.AddField(
            model_name="scene",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="scene",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        # JobLog — created_at already exists, add updated_at
        migrations.AddField(
            model_name="joblog",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
    ]
