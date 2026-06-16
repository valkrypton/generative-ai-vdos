import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Project",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("prompt", models.TextField()),
                ("title", models.CharField(blank=True, default="", max_length=200)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("DRAFT", "Draft"),
                            ("PLANNING", "Planning"),
                            ("REVIEW", "Review"),
                            ("GENERATING", "Generating"),
                            ("DONE", "Done"),
                            ("FAILED", "Failed"),
                        ],
                        default="DRAFT",
                        max_length=20,
                    ),
                ),
                ("shot_plan", models.JSONField(blank=True, null=True)),
                ("image_backend", models.CharField(blank=True, default="", max_length=50)),
                ("animate", models.BooleanField(default=False)),
                (
                    "narrator_voice",
                    models.CharField(blank=True, default="", max_length=100),
                ),
                ("music", models.CharField(blank=True, default="", max_length=200)),
                ("error", models.TextField(blank=True, default="")),
                ("stale", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "owner",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="projects",
                        to="accounts.userprofile",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Scene",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("index", models.IntegerField()),
                (
                    "image_path",
                    models.CharField(blank=True, default="", max_length=500),
                ),
                (
                    "image_status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("RUNNING", "Running"),
                            ("DONE", "Done"),
                            ("FAILED", "Failed"),
                        ],
                        default="PENDING",
                        max_length=20,
                    ),
                ),
                (
                    "image_provider",
                    models.CharField(blank=True, default="", max_length=50),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="scenes",
                        to="projects.project",
                    ),
                ),
            ],
            options={
                "ordering": ["index"],
                "unique_together": {("project", "index")},
            },
        ),
        migrations.CreateModel(
            name="JobLog",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("stage", models.CharField(max_length=50)),
                (
                    "level",
                    models.CharField(
                        choices=[
                            ("info", "Info"),
                            ("warn", "Warn"),
                            ("error", "Error"),
                        ],
                        default="info",
                        max_length=10,
                    ),
                ),
                ("message", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="logs",
                        to="projects.project",
                    ),
                ),
            ],
            options={
                "ordering": ["created_at"],
            },
        ),
    ]
