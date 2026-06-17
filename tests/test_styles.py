"""Tests for pipeline.styles — preset resolution and LLM instruction injection."""

from __future__ import annotations

from pipeline.styles import PRESETS, inject_style_instruction, resolve_style


def test_resolve_none_returns_none():
    assert resolve_style(None) is None


def test_resolve_known_preset():
    result = resolve_style("cinematic")
    assert result == PRESETS["cinematic"]
    assert result["style_prefix"]
    assert result["global_negative"]
    assert result["music_mood"]


def test_resolve_case_insensitive():
    assert resolve_style("CINEMATIC") == PRESETS["cinematic"]
    assert resolve_style("Anime") == PRESETS["anime"]


def test_resolve_list_exits_zero():
    try:
        resolve_style("list")
        assert False, "should have called sys.exit"
    except SystemExit as e:
        assert e.code == 0


def test_resolve_unknown_raises():
    try:
        resolve_style("nonexistent")
        assert False, "should have raised ValueError"
    except ValueError as e:
        assert "nonexistent" in str(e)


def test_resolve_custom_prefix():
    result = resolve_style("custom:oil painting, thick brush strokes")
    assert result["style_prefix"] == "oil painting, thick brush strokes"
    assert result["global_negative"] is None
    assert result["music_mood"] is None


def test_inject_full_preset():
    preset = PRESETS["storybook"]
    text = inject_style_instruction(preset)
    assert preset["style_prefix"] in text
    assert preset["global_negative"] in text
    assert preset["music_mood"] in text
    assert "STYLE CONSTRAINT" in text


def test_inject_custom_only_constrains_prefix():
    custom = {"style_prefix": "oil painting", "global_negative": None, "music_mood": None}
    text = inject_style_instruction(custom)
    assert "oil painting" in text
    assert "global_negative" not in text
    assert "music_mood" not in text


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  PASS {name}")
    print("all tests passed")
