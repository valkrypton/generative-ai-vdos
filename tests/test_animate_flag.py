"""Regression tests: the animate flag must reach both plan generation and the
consistency review so `pipeline.run --animate` actually animates (and a default
run stays animation-free).
"""
from unittest.mock import MagicMock, patch

import pipeline.script_agent as sa


def test_generate_shot_plan_animate_true_omits_disabled_instruction():
    with patch.object(sa, "_parse_with_llm", return_value="PLAN") as m:
        sa.generate_shot_plan("topic", animate=True)
    system_extra = m.call_args.kwargs.get("system_extra")
    assert system_extra is None or "ANIMATION DISABLED" not in system_extra


def test_generate_shot_plan_animate_false_injects_disabled_instruction():
    with patch.object(sa, "_parse_with_llm", return_value="PLAN") as m:
        sa.generate_shot_plan("topic", animate=False)
    system_extra = m.call_args.kwargs.get("system_extra")
    assert system_extra is not None and "ANIMATION DISABLED" in system_extra


def _fake_plan():
    plan = MagicMock()
    plan.model_dump_json.return_value = "{}"
    return plan


def test_consistency_review_animate_true_uses_cap_clause():
    with patch.object(sa, "_parse_with_llm", return_value="PLAN") as m:
        sa.consistency_review(_fake_plan(), animate=True)
    prompt = m.call_args.args[0]
    assert "ANIMATE CAP" in prompt
    assert "ANIMATION DISABLED" not in prompt


def test_consistency_review_animate_false_uses_disabled_clause():
    with patch.object(sa, "_parse_with_llm", return_value="PLAN") as m:
        sa.consistency_review(_fake_plan(), animate=False)
    prompt = m.call_args.args[0]
    assert "ANIMATION DISABLED" in prompt


def test_refine_plan_threads_animate_into_review():
    with patch.object(sa, "_parse_with_llm", return_value="PLAN") as m:
        sa.refine_plan(_fake_plan(), model="m", animate=True, polish=False, review=True)
    prompt = m.call_args.args[0]
    assert "ANIMATE CAP" in prompt
    assert "ANIMATION DISABLED" not in prompt
