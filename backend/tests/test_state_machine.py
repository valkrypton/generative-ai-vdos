import uuid as _uuid
from django.test import TestCase
from apps.users.models import UserProfile
from apps.projects.models import Project


def make_project_in(status):
    uid = _uuid.uuid4().hex[:8]
    user = UserProfile.objects.create(
        cognito_sub=f"sub-{status}-{uid}", email=f"{status}-{uid}@example.com"
    )
    p = Project.objects.create(owner=user, prompt="test")
    Project.objects.filter(pk=p.pk).update(status=status)
    p.refresh_from_db()
    return p


class ValidTransitionsTest(TestCase):
    def test_draft_to_planning(self):
        p = make_project_in(Project.Status.DRAFT)
        p.transition_status(Project.Status.PLANNING)
        self.assertEqual(p.status, Project.Status.PLANNING)

    def test_planning_to_review(self):
        p = make_project_in(Project.Status.PLANNING)
        p.transition_status(Project.Status.REVIEW)
        self.assertEqual(p.status, Project.Status.REVIEW)

    def test_planning_to_failed(self):
        p = make_project_in(Project.Status.PLANNING)
        p.transition_status(Project.Status.FAILED)
        self.assertEqual(p.status, Project.Status.FAILED)

    def test_review_to_generating(self):
        p = make_project_in(Project.Status.REVIEW)
        p.transition_status(Project.Status.GENERATING)
        self.assertEqual(p.status, Project.Status.GENERATING)

    def test_generating_to_done(self):
        p = make_project_in(Project.Status.GENERATING)
        p.transition_status(Project.Status.DONE)
        self.assertEqual(p.status, Project.Status.DONE)

    def test_generating_to_failed(self):
        p = make_project_in(Project.Status.GENERATING)
        p.transition_status(Project.Status.FAILED)
        self.assertEqual(p.status, Project.Status.FAILED)

    def test_failed_to_generating(self):
        p = make_project_in(Project.Status.FAILED)
        p.transition_status(Project.Status.GENERATING)
        self.assertEqual(p.status, Project.Status.GENERATING)


class InvalidTransitionsTest(TestCase):
    def _assert_raises(self, from_status, to_status):
        p = make_project_in(from_status)
        with self.assertRaises(ValueError):
            p.transition_status(to_status)

    def test_done_to_anything(self):
        for s in [Project.Status.DRAFT, Project.Status.PLANNING,
                  Project.Status.REVIEW, Project.Status.GENERATING,
                  Project.Status.FAILED]:
            with self.subTest(to=s):
                self._assert_raises(Project.Status.DONE, s)

    def test_review_to_failed(self):
        self._assert_raises(Project.Status.REVIEW, Project.Status.FAILED)

    def test_review_to_done(self):
        self._assert_raises(Project.Status.REVIEW, Project.Status.DONE)

    def test_draft_to_done(self):
        self._assert_raises(Project.Status.DRAFT, Project.Status.DONE)

    def test_failed_to_review(self):
        self._assert_raises(Project.Status.FAILED, Project.Status.REVIEW)
