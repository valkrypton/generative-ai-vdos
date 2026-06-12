# Generative AI Videos — YouTube Pipeline

Topic in → finished video out: LLM shot plan → AI images → optional image-to-video
animation (Wan) → voiceover → FFmpeg assembly with captions and music.
Cost per video: ~$0.001-0.01 (script) + ~$0.03-0.20 (images, backend-dependent) — or **$0 in placeholder mode**.

## Setup

```bash
brew install ffmpeg-full                 # required for assembly (plain `ffmpeg` lacks
                                          # libass/freetype, so captions can't be burned in)
cd youtube-pipeline
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                     # then fill in your keys; load with:
set -a && source .env && set +a
```

Keys (any one LLM key + optionally one image key):

- `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` — shot-plan stage (model auto-picked from whichever is set)
- Image backends, first available wins (or force with `--image-backend`):
  1. `REPLICATE_API_TOKEN` + `pip install replicate` → Flux Schnell (~$0.003/image)
  2. `OPENAI_API_KEY` → gpt-image-1 (~$0.01-0.02/image)
  3. `PEXELS_API_KEY` → free stock photos (pexels.com/api, no billing)
  4. nothing → free PIL gradient placeholders
- Video backend (optional, `--animate` turns scene stills into real motion clips):
  - `DASHSCOPE_API_KEY` → Wan image-to-video via Alibaba Model Studio.
    New intl (Singapore) accounts get ~1650s of free video credit for 90 days
    (≈330 five-second clips); after that ~$0.10-0.25 per clip.

## Usage

```bash
# 1. Generate the shot plan (stops at the review gate)
python -m pipeline.run "Why octopuses have three hearts"

# 2. Review/edit output/<slug>/shot_plan.json — the cheap artifact

# 3. Generate assets and render
python -m pipeline.run "Why octopuses have three hearts" --approve

# Step-by-step instead: stop after any stage
python -m pipeline.run "..." --approve --until images

# Force an image backend / a friendlier folder name
python -m pipeline.run "..." --approve --image-backend pexels --name octopus-hearts

# Regenerate one scene's image after editing its image_prompt in shot_plan.json
python -m pipeline.images output/<slug> --scene 7

# Animate stills into motion clips (Wan, needs DASHSCOPE_API_KEY)
python -m pipeline.run "..." --approve --animate
python -m pipeline.video output/<slug>             # or per work dir / re-run failures
python -m pipeline.video output/<slug> --scene 3   # or a single scene
```

Output lands in `output/<slug>/final.mp4`. Each stage records completion in
`output/<slug>/state.json`, so re-running skips finished stages. To redo a stage,
remove its name from `state.json` (and delete its artifacts).

## Music

Drop license-safe mp3s (e.g. from the YouTube Audio Library) into
`music/<mood>/` — moods: `calm`, `upbeat`, `dramatic`, `mysterious`, `inspiring`.
The shot plan picks the mood; the assembler picks a random track from that folder.
No music folder → video renders without a music bed.

## Architecture

```
pipeline/
  schema.py        ShotPlan — the JSON contract everything consumes
  script_agent.py  Stage 1: LLM -> validated ShotPlan (Anthropic or OpenAI by model name)
  images/          Stage 2: provider registry — flux.py, gpt_image.py, pexels.py,
                   placeholder.py; per-scene fallback chain; `python -m pipeline.images`
                   regenerates single scenes
  video/           Stage 2.5 (optional): image-to-video providers — wan.py (DashScope).
                   Batch-submits all scenes as server-side tasks, polls concurrently.
                   Fail-soft: a failed scene stays a Ken Burns still.
  voiceover.py     Stage 3: edge-tts (free) — also yields word timestamps for captions
  assemble.py      Stage 4: FFmpeg — animated clip if video/scene_NN.mp4 exists,
                   else Ken Burns still -> concat -> captions + music
  run.py           resumable runner + human review gate
```

Adding an image backend: subclass `ImageProvider` (`pipeline/images/base.py`) in a
new module and append an instance to `PROVIDERS` in `pipeline/images/__init__.py`.
If a backend fails mid-run (moderation block, no results, network), the next
available one is tried automatically, ending at the placeholder.

Scene durations are derived from the voiceover audio length — the shot plan
doesn't guess them.

## Not yet built (Phase 2)

- YouTube upload (Data API + OAuth)
- Thumbnail generation
- Batch/cron mode
