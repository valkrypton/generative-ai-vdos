# Generative AI Videos — Automated YouTube Pipeline

Turn a topic (or a full script) into a finished, narrated 1080p video — automatically.

```
"Why octopuses have three hearts"
        │
        ▼
┌─────────────────┐   ┌──────────────┐   ┌──────────────────┐   ┌───────────┐   ┌──────────────┐
│ 1. Shot plan    │ → │ 2. Images    │ → │ 2.5 Animate      │ → │ 3. Voice  │ → │ 4. Assemble  │
│ LLM → JSON      │   │ AI image gen │   │ (optional)       │   │ edge-tts  │   │ FFmpeg       │
│ scenes/prompts  │   │ per scene    │   │ image-to-video   │   │ free TTS  │   │ final.mp4    │
└─────────────────┘   └──────────────┘   └──────────────────┘   └───────────┘   └──────────────┘
        ▲ human review gate here — edit the JSON before money is spent
```

**Cost per video:** ~$0.001–0.01 (script) + ~$0.03–0.20 (images) + $0 (voice) — or **$0 end-to-end in placeholder mode**. Optional animation: free trial credit, then ~$0.10–0.25 per 5s clip.

## Features

- **Multi-provider by design** — every external service is a pluggable backend with automatic fallback. No key? It still runs (placeholder images, no music).
- **Human review gate** — the LLM produces a cheap, editable `shot_plan.json` first; nothing expensive runs until you approve.
- **Resumable** — every stage records completion in `state.json`; re-runs skip finished work. Crashed mid-images? Re-run and it continues.
- **Real motion (optional)** — scene stills can be animated into video clips via image-to-video models; scenes that fail just stay as Ken Burns stills.
- **Free captions** — word-level timestamps come from the TTS stream itself, no Whisper pass needed.

## Requirements

- **macOS or Linux** with Python 3.9+
- **FFmpeg with libass** (for burned-in captions):
  - macOS: `brew install ffmpeg-full && brew link --overwrite ffmpeg-full`
    (plain `ffmpeg` from Homebrew lacks the `subtitles` filter)
  - Debian/Ubuntu: `sudo apt install ffmpeg` (includes libass)
- At least one LLM API key (OpenAI or Anthropic) for the shot-plan stage

## Installation

```bash
git clone git@github.com:awais786/generative-ai-vdos.git
cd generative-ai-vdos

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # then edit it and add your keys
# (the pipeline auto-loads .env — no manual sourcing needed)
```

### API keys

| Key | Used for | Where to get it | Cost |
|---|---|---|---|
| `OPENAI_API_KEY` | Shot plan (gpt-4o-mini) + images (gpt-image-1) | [platform.openai.com](https://platform.openai.com/api-keys) | ~$0.001/plan, ~$0.01–0.02/image |
| `ANTHROPIC_API_KEY` | Shot plan (Claude) — alternative to OpenAI | [console.anthropic.com](https://console.anthropic.com/) | ~$0.001/plan |
| `REPLICATE_API_TOKEN` | Images via Flux Schnell (also `pip install replicate`) | [replicate.com](https://replicate.com/) | ~$0.003/image |
| `PEXELS_API_KEY` | Free stock photos instead of AI images | [pexels.com/api](https://www.pexels.com/api/) | free |
| `DASHSCOPE_API_KEY` | Images (`qwen-image`, free quota) + animate stills into video clips (Wan i2v) | [Alibaba Model Studio](https://modelstudio.console.alibabacloud.com) — **pick the Singapore region**; new accounts get free image quota and ~1,650s of video credit (90 days) | free quota, then ~$0.02/image, ~$0.10–0.25/clip |

Only one LLM key and zero image keys are strictly required — with no image key the pipeline renders gradient placeholders so you can test the whole flow for free.

## Usage

```bash
# 1. Generate the shot plan only (stops at the review gate)
python -m pipeline.run "Why octopuses have three hearts"

# 2. Review and edit output/<slug>/shot_plan.json — narration, image prompts,
#    music mood. This is the cheap artifact; fix it before spending on assets.

# 3. Generate everything and render
python -m pipeline.run "Why octopuses have three hearts" --approve
# → output/<slug>/final.mp4
```

### Step-by-step runs

```bash
python -m pipeline.run "..." --approve --until images    # stop after images
python -m pipeline.run "..." --approve --until voice     # ... after voiceover
python -m pipeline.run "..." --approve                   # finish the rest
```

### Useful flags

| Flag | What it does |
|---|---|
| `--name octopus` | Friendly output folder name instead of the topic slug |
| `--image-backend pexels` | Force a backend: `flux-schnell`, `qwen-image`, `gpt-image-1`, `pexels`, `placeholder` |
| `--animate` | Animate scene stills into motion clips (needs `DASHSCOPE_API_KEY`) |
| `--model claude-haiku-4-5` | LLM for the shot plan (auto-picked from available keys) |
| `--voice en-GB-SoniaNeural` | Any [edge-tts voice](https://github.com/rany2/edge-tts#custom-voice) |

### Per-scene fixes

```bash
# Regenerate one image after editing its image_prompt in shot_plan.json
python -m pipeline.images output/<slug> --scene 3

# Animate all scenes / one scene of an existing video
python -m pipeline.video output/<slug>
python -m pipeline.video output/<slug> --scene 3
```

To redo a whole stage: remove its name from `output/<slug>/state.json` and delete its artifacts, then re-run.

### Background music

Drop royalty-free mp3s into `music/<mood>/` (moods: `calm`, `upbeat`, `dramatic`, `mysterious`, `inspiring`). The assembler ducks the track under the voiceover. No folder → no music bed, still renders fine.

## Architecture

```
pipeline/
  run.py           CLI orchestrator — resumable stages, review gate
  schema.py        ShotPlan/Scene pydantic models — the contract between stages
  script_agent.py  Stage 1: topic → ShotPlan via structured LLM output
                   (provider picked by model name: gpt-* → OpenAI, claude-* → Anthropic)
  images/          Stage 2: image providers
    base.py          ImageProvider interface
    flux.py          Flux Schnell via Replicate
    qwen_image.py    Qwen via DashScope (free quota, shares the Wan key)
    gpt_image.py     OpenAI gpt-image-1
    pexels.py        free stock photos
    placeholder.py   PIL gradients, $0, always available
  video/           Stage 2.5 (optional): image-to-video providers
    base.py          VideoProvider interface (+ async submit/poll/download protocol)
    wan.py           Wan via Alibaba DashScope REST
  voiceover.py     Stage 3: edge-tts, word timestamps captured from the stream
  assemble.py      Stage 4: FFmpeg — per-scene clips (animated clip if present,
                   else Ken Burns on the still) → concat → captions + music mix
```

Key design points for contributors:

- **`schema.py` is the contract.** Stages only communicate through `ShotPlan` JSON and files in the work dir (`images/scene_NN.png`, `video/scene_NN.mp4`, `audio/scene_NN.mp3` + `.words.json`). Any stage can be re-run or replaced independently.
- **Scene durations come from the voiceover audio**, never from the plan — the assembler measures each mp3.
- **Image fallback chain:** if the chosen backend fails on a scene (moderation block, no search results, network error), the next available provider is tried automatically, ending at the placeholder. A single bad scene never kills a run.
- **Video providers are fail-soft:** a scene whose animation fails or times out stays a Ken Burns still. Wan tasks are submitted for all scenes at once and polled concurrently — n clips take roughly the wall-clock time of one.

## Adding a provider

**Image backend** — subclass `ImageProvider` in a new module under `pipeline/images/`:

```python
from .base import ImageProvider

class MyProvider(ImageProvider):
    name = "my-backend"
    cost_note = "~$0.005/image"

    def available(self) -> bool:
        return bool(os.environ.get("MY_API_KEY"))

    def generate(self, prompt, path, query=None) -> None:
        ...  # write a 1920x1080 png to path, or raise to trigger fallback
```

then append an instance to `PROVIDERS` in `pipeline/images/__init__.py`. List order = auto-pick priority. Done — CLI flags, fallback, and single-scene regen all pick it up.

**Video backend** — same pattern with `VideoProvider` in `pipeline/video/`. Implement `generate()` for sequential use; optionally also `submit()`/`poll()`/`download()` to get concurrent batch animation for free.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ffmpeg failed: ... No such filter: 'subtitles'` | Install `ffmpeg-full` (macOS) — plain Homebrew ffmpeg lacks libass |
| Images are colored gradients with text | No image key found — set `OPENAI_API_KEY`, `PEXELS_API_KEY`, or `REPLICATE_API_TOKEN` |
| `moderation_blocked` on an image | The fallback chain handles it; to retry, soften the `image_prompt` in `shot_plan.json` and run `python -m pipeline.images output/<slug> --scene N` |
| Wan: `no video backend configured` | Set `DASHSCOPE_API_KEY`; free credit requires a Singapore-region Model Studio account |
| Stage re-runs do nothing | Stage already in `state.json` `done` list — remove it there |

## Roadmap

- YouTube upload (Data API + OAuth)
- Thumbnail generation from the best scene
- 9:16 portrait mode for Shorts/Reels
- Scene transitions
