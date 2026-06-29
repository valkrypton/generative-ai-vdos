from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0001_initial"),
    ]

    operations = [
        migrations.RenameField(
            model_name="scene",
            old_name="image_status",
            new_name="media_status",
        ),
        migrations.RenameField(
            model_name="scene",
            old_name="image_provider",
            new_name="media_provider",
        ),
    ]
