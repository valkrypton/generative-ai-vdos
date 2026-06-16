from django.test import TestCase
from apps.accounts.models import UserProfile
from apps.projects.models import Project, JobLog


def make_project():
    user = UserProfile.objects.create(cognito_sub="sub-log", email="log@example.com")
    return Project.objects.create(owner=user, prompt="test")


class JobLogTest(TestCase):
    def setUp(self):
        self.project = make_project()

    def test_create_log_entry(self):
        log = JobLog.objects.create(
            project=self.project,
            stage="plan",
            level="info",
            message="Shot plan ready.",
        )
        self.assertEqual(log.stage, "plan")
        self.assertEqual(log.level, "info")
        self.assertIsNotNone(log.created_at)

    def test_cascade_delete_with_project(self):
        JobLog.objects.create(
            project=self.project, stage="plan", level="info", message="ok"
        )
        pid = self.project.id
        self.project.delete()
        self.assertFalse(JobLog.objects.filter(project_id=pid).exists())

    def test_multiple_entries_per_project(self):
        for i in range(3):
            JobLog.objects.create(
                project=self.project, stage="images", level="info", message=f"scene {i}"
            )
        self.assertEqual(JobLog.objects.filter(project=self.project).count(), 3)

    def test_ordering_is_chronological(self):
        JobLog.objects.create(
            project=self.project, stage="plan", level="info", message="first"
        )
        JobLog.objects.create(
            project=self.project, stage="images", level="info", message="second"
        )
        stages = list(
            JobLog.objects.filter(project=self.project).values_list("stage", flat=True)
        )
        self.assertEqual(stages, ["plan", "images"])
