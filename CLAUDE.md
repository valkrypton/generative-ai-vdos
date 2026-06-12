# CLAUDE.md

AI video pipeline: rough text idea → shot plan JSON → AI images → optional animation →
TTS voiceover → FFmpeg assembly → `output/<name>/final.mp4`. See README.md for the full
user guide; this file covers what an agent needs to work on the codebase safely.

## Commands

```bash
source .venv/bin/activate                  # python 3.9 venv at repo root
python -m pipeline.refine "idea"           # plan + auto-polish (stage 1, ~$0.001)
python -m pipeline.refine --change "..."   # revise latest plan
python -m pipeline.images                  # stage 2 (free via qwen)
python -m pipeline.video                   # stage 2.5 — SPENDS Wan credit (~5s/scene)
python -m pipeline.voiceover               # stage 3 (free)
python -m pipeline.assemble [--music f]    # stage 4 (free, local ffmpeg)
```

All stage commands default to the most recently touched `output/*/` folder
(`latest_work_dir()` in `pipeline/run.py`); pass a folder to target an older video.
`python -m pipeline.run "topic" --approve --animate` is the one-shot path with
resumable `state.json`.

There is no test suite. Verify changes by running stages against a copy of
`examples/the-sharing-berry/` with `--backend placeholder` (free, no keys needed).

## Money rules

- **Never run `pipeline.video` (Wan animation) without the user asking** — it spends
  the limited free credit (~1,650s per account, ~5s/scene). Same for adding paid
  backends to a run.
- Images via `qwen-image` and plans via `gpt-4o-mini` are effectively free; still,
  show the user the plan/images at review gates before generating downstream assets.
- The user reviews artifacts between stages by preference: plan → images → the rest.

## Architecture in 30 seconds

- `pipeline/schema.py` is the contract: `ShotPlan`/`Scene`/`Character`. Stages
  communicate ONLY via `shot_plan.json` + files in the work dir
  (`images/scene_NN.png`, `video/scene_NN.mp4`, `audio/scene_NN.mp3` + `.words.json`).
- Image/video backends are provider plugins: subclass the base in
  `pipeline/images/base.py` or `pipeline/video/base.py`, append an instance to
  `PROVIDERS` in the package `__init__.py`. Order = auto-pick priority; per-scene
  fallback chain ends at the always-available placeholder.
- Scene durations come from measuring the voiceover mp3s in `assemble.py` —
  never from the plan.
- `.env` at repo root auto-loads (`pipeline/env.py`); empty values are ignored.
  Keys: `OPENAI_API_KEY`, `DASHSCOPE_API_KEY` (+ optional `DASHSCOPE_API_URL`
  workspace endpoint), see `.env.example`. Never commit `.env`.

## Hard-won gotchas (do not re-litigate)

- **Character consistency is enforced by code, not the LLM.** LLMs cannot repeat
  descriptions verbatim across scenes — that's why `characters` + `{name}`
  placeholders + `ShotPlan.expand()` exist. Never put a character's look inline in a
  scene prompt; never put pose/emotion in a character description.
- **Image models draw negated words** ("no beard" → beard). Unwanted traits go in
  `scene.negative_prompt`. If qwen still refuses (strong priors), regenerate that one
  scene with `--backend gpt-image-1` — it follows instructions much better.
- Wan model/resolution/duration are **hardcoded constants** in `pipeline/video/wan.py`
  (wan2.2-i2v-flash, 720P, 5s) by user decision — don't make them env vars.
- macOS needs `ffmpeg-full` (plain Homebrew ffmpeg lacks libass → no `subtitles`
  filter). ffmpeg path args must be absolute (`.resolve()`) when `cwd=work_dir`.
- edge-tts needs `boundary="WordBoundary"` to emit word timestamps (captions
  depend on them).
- Subscribe/CTA scenes are only for listicle-style videos — story/dialogue videos
  end on the story's final beat (enforced in the system prompt).
- Browser automation of AI web UIs (AI Studio, Flow, etc.) was proposed and
  rejected — API-only integrations.

## Conventions

- Python 3.9 compatible (no `X | None`, use `Optional`).
- Stage CLIs live in each module (`main()` + `__main__.py` for packages); keep new
  stages consistent with that pattern.
- `output/`, `music/`, `.env`, `.venv` are gitignored — never force-add them.
- CC-BY music in `music/` requires attribution (see `music/ATTRIBUTION.txt`).
