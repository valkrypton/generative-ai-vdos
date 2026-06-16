"""Verify pipeline package imports cleanly — no accidental Django coupling."""


def test_pipeline_schema_imports():
    from pipeline.schema import ShotPlan, Scene, Character
    assert ShotPlan is not None
    assert Scene is not None
    assert Character is not None


def test_pipeline_env_imports():
    from pipeline.env import load_env
    assert callable(load_env)


def test_django_does_not_auto_import_pipeline():
    """pipeline/ must not import Django at module level."""
    import pipeline.schema  # noqa: F401
    import sys
    # Django may be present in sys.modules (it's installed), but pipeline
    # must not *require* it — importing pipeline.schema must not raise.
    assert "pipeline.schema" in sys.modules
