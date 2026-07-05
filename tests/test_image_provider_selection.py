"""Regression tests for image backend auto-pick — the documented "first
available backend" behavior, with gpt-image-1 kept out of auto-selection
(money rule)."""
import pytest

import pipeline.images as images


def test_get_provider_none_autopicks_first_available():
    # With no API keys in the test env only PlaceholderProvider is available().
    assert images.get_provider(None).name == "placeholder"


def test_get_provider_none_never_autopicks_gpt_image(monkeypatch):
    # Even if gpt-image-1 were the only "available" backend, auto-pick must skip
    # it and raise rather than silently spend money.
    for p in images.PROVIDERS:
        monkeypatch.setattr(p, "available", (lambda: True) if p.name == "gpt-image-1"
                            else (lambda: False))
    with pytest.raises(RuntimeError):
        images.get_provider(None)


def test_explicit_gpt_image_still_selectable(monkeypatch):
    # The paid backend remains reachable when named explicitly.
    for p in images.PROVIDERS:
        if p.name == "gpt-image-1":
            monkeypatch.setattr(p, "available", lambda: True)
    assert images.get_provider("gpt-image-1").name == "gpt-image-1"
    assert images.get_provider("openai").name == "gpt-image-1"  # alias
