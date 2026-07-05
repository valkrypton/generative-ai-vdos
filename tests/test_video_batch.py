"""Regression test: a single scene's download failure must not abort the whole
animate batch — the other clips still render (fail-soft, per the module docstring).
"""
import pipeline.video as video
from pipeline.schema import Scene, ShotPlan


class _FlakyProvider:
    """submit/poll succeed for every scene; download raises for scene index 1."""

    name = "flaky"

    def submit(self, prompt, image_path):
        return f"task-{image_path.stem}"

    def poll(self, task_id):
        return f"http://cdn/{task_id}.mp4"

    def download(self, url, out_path):
        if "scene_01" in url:
            raise RuntimeError("simulated transient download error")
        out_path.write_bytes(b"fake-mp4")


def _plan(n):
    return ShotPlan(
        title="t", description="d", tags=["x"], music_mood="calm",
        style_prefix="s", characters=[],
        scenes=[Scene(narration="n", media_prompt=f"shot {i}", animate=True)
                for i in range(n)],
    )


def test_batch_survives_single_download_failure(tmp_path, monkeypatch):
    # Don't wait 15s between polls in the test.
    monkeypatch.setattr(video, "POLL_INTERVAL", 0)
    images = tmp_path / "images"
    images.mkdir()
    out = tmp_path / "video"
    out.mkdir()

    # Must not raise despite scene 1's download blowing up.
    video._animate_batch(_FlakyProvider(), _plan(3), images, out, [0, 1, 2])

    assert (out / "scene_00.mp4").exists()
    assert not (out / "scene_01.mp4").exists()   # failed download stays a still
    assert (out / "scene_02.mp4").exists()
