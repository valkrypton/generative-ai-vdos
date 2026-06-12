# Generative AI Videos — Automated YouTube Pipeline

Turn a rough idea (or a full script) into a finished, narrated 1080p video — automatically.

```
"a thief gets caught and learns a lesson"
        │
        ▼
┌─────────────────┐   ┌──────────────┐   ┌──────────────────┐   ┌───────────┐   ┌──────────────┐
│ 1. Shot plan    │ → │ 2. Images    │ → │ 2.5 Animate      │ → │ 3. Voice  │ → │ 4. Assemble  │
│ refine → JSON   │   │ AI image gen │   │ (optional)       │   │ edge-tts  │   │ FFmpeg       │
│ review + iterate│   │ per scene    │   │ image-to-video   │   │ free TTS  │   │ final.mp4    │
└─────────────────┘   └──────────────┘   └──────────────────┘   └───────────┘   └──────────────┘
   review gates: iterate on the plan, then inspect images, before any video credit is spent
```

**Cost per video:** ~$0.001 (script) + $0 images (Qwen free quota) + $0 voice — or **$0 end-to-end in placeholder mode**. Optional animation: free trial credit, then ~$0.10–0.25 per 5s clip.

## Features

- **Refine-and-iterate workflow** — rough text in, reviewable shot plan out; revise it with plain-English feedback before anything is generated.
- **Consistent characters** — define each recurring character once; the pipeline substitutes the full description into every scene's prompts (code-enforced, not LLM-hoped).
- **Multi-provider with fallback** — 5 image backends, auto-picked by available keys; a failed scene falls through to the next backend instead of killing the run.
- **Real motion (optional)** — stills animated into video clips (Wan i2v); failed scenes gracefully stay as Ken Burns stills.
- **Dialogue voices** — per-scene TTS voices (e.g. two characters talking, any language edge-tts supports, including Urdu).
- **Free captions + text overlays** — word-synced subtitles from TTS timestamps; `on_screen_text` rendered as styled titles.
- **Resumable** — every stage records completion; re-runs skip finished work.

## Requirements

- **macOS or Linux** with Python 3.9+
- **FFmpeg with libass** (for burned-in captions):
  - macOS: `brew install ffmpeg-full && brew link --overwrite ffmpeg-full`
    (plain `ffmpeg` from Homebrew lacks the `subtitles` filter)
  - Debian/Ubuntu: `sudo apt install ffmpeg` (includes libass)

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
| `DASHSCOPE_API_KEY` | Images (`qwen-image`, free quota) + animation (Wan i2v) | [Alibaba Model Studio](https://modelstudio.console.alibabacloud.com) — **pick the Singapore region**; new accounts get free image quota and ~1,650s of video credit (90 days) | free quota, then ~$0.02/image, ~$0.10–0.25/clip |
| `REPLICATE_API_TOKEN` | Images via Flux Schnell (also `pip install replicate`) | [replicate.com](https://replicate.com/) | ~$0.003/image |
| `PEXELS_API_KEY` | Free stock photos instead of AI images | [pexels.com/api](https://www.pexels.com/api/) | free |

Minimum: one LLM key (OpenAI or Anthropic). With no image key the pipeline renders gradient placeholders so the whole flow can be tested for $0.

## Workflow

### Step 1 — refine: rough idea → reviewable plan

```bash
python -m pipeline.refine "Messi and Ronaldo chat about the World Cup with their friend Awais. 4-6 scenes, three distinct male English voices."
```

Prints the full plan — title, character cards, every scene's narration / expanded image prompt / motion / voice — and writes it to `output/<title-slug>/shot_plan.json`. Costs ~$0.001, generates nothing else yet.

Iterate until it's right (each command defaults to the most recent video):

```bash
python -m pipeline.refine --change "make Awais 48 and clean-shaven, put him in the stadium"
python -m pipeline.refine                      # view the current plan again
```

You can also edit `shot_plan.json` directly in an editor.

### Step 2 — images (review before spending video credit)

```bash
python -m pipeline.images        # prints a character-consistency check, then generates
open output/<name>/images        # inspect

# a scene came out wrong? fix its prompt (or negative_prompt) and redo just that one:
python -m pipeline.images --scene 2
# or force the more obedient (paid) backend for a stubborn scene:
python -m pipeline.images --scene 2 --backend gpt-image-1
```

### Steps 3–5 — animate, voice, assemble

```bash
python -m pipeline.video         # ~5s credit per scene; skips scenes that already have clips
python -m pipeline.voiceover     # per-scene voices from the plan, word timestamps for captions
python -m pipeline.assemble      # music picked by mood from music/, or:
python -m pipeline.assemble --music path/to/track.mp3
open output/<name>/final.mp4
```

All stage commands accept an explicit folder (`python -m pipeline.images output/<name>`) to work on an older video instead of the latest.

### One-shot alternative

```bash
python -m pipeline.run "topic" --approve --animate    # everything in one command
```

`pipeline.run` keeps a review gate after the plan (omit `--approve` to stop there), supports `--until <stage>`, and resumes from `state.json` if interrupted.

## The shot plan format

`shot_plan.json` is the contract every stage consumes. The important fields:

```jsonc
{
  "title": "...", "description": "...", "tags": [...],
  "music_mood": "calm | upbeat | chill | dramatic | mysterious | inspiring",
  "style_prefix": "vibrant 3D cartoon animation style, ...",   // prepended to every image prompt
  "characters": [
    { "name": "thief",
      "description": "a mid-30s man with short black hair and stubble, wearing a black zip-up hoodie, dark blue jeans and white sneakers" }
  ],
  "scenes": [
    {
      "narration": "What would you do if the cops were closing in?",   // the spoken line
      "image_prompt": "{thief} crouching by the locker, picking the lock",
      "motion": "{thief} is talking, lips moving as he speaks",         // optional, drives animation
      "voice": "en-US-BrianNeural",          // optional, per-scene speaker (dialogue)
      "on_screen_text": "Caught!",           // optional, styled title overlay
      "negative_prompt": "beard, mustache"   // optional, things the image must NOT contain
    }
  ]
}
```

**Character consistency:** scenes are generated independently, so the pipeline substitutes each character's full description wherever `{name}` (or the bare name) appears in `image_prompt`/`motion`. Change a character's look in one place; every scene follows.

**Negatives:** image models ignore negated text — "no beard" *draws a beard*. Put unwanted traits in `negative_prompt` instead (used by backends that support it).

## Architecture

```
pipeline/
  refine.py        idea -> plan -> iterate (--change) -> print review
  run.py           one-shot orchestrator — resumable stages, review gate
  schema.py        ShotPlan/Scene/Character pydantic models + {placeholder} expansion
  script_agent.py  LLM -> validated ShotPlan (OpenAI or Anthropic by model name)
  env.py           zero-dependency .env auto-loader
  images/          Stage 2: provider registry + per-scene fallback chain
    flux.py qwen_image.py gpt_image.py pexels.py placeholder.py
  video/           Stage 2.5 (optional): image-to-video
    wan.py           Wan via DashScope REST — batch submit, concurrent polling, fail-soft
  voiceover.py     Stage 3: edge-tts, per-scene voices, word timestamps
  assemble.py      Stage 4: FFmpeg — animated clips or Ken Burns, captions, overlays, music
```

Design rules for contributors:

- **`schema.py` is the contract.** Stages communicate only through `ShotPlan` JSON and files in the work dir (`images/scene_NN.png`, `video/scene_NN.mp4`, `audio/scene_NN.mp3` + `.words.json`). Any stage can be re-run or replaced independently.
- **Scene durations come from the voiceover audio** — the assembler measures each mp3; the plan never guesses timing.
- **Consistency is enforced by code, not the LLM.** LLMs reliably fail at repeating descriptions verbatim across scenes; `ShotPlan.expand()` does the substitution deterministically.
- **Fail-soft everywhere:** image backends fall through a chain ending at the free placeholder; a failed animation leaves a Ken Burns still; assembly errors name the missing stage.

### Adding an image backend

```python
# pipeline/images/my_backend.py
from .base import ImageProvider

class MyProvider(ImageProvider):
    name = "my-backend"
    cost_note = "~$0.005/image"

    def available(self) -> bool:
        return bool(os.environ.get("MY_API_KEY"))

    def generate(self, prompt, path, query=None, negative=None) -> None:
        ...  # write a 1920x1080 png to path, or raise to trigger fallback
```

then append an instance to `PROVIDERS` in `pipeline/images/__init__.py` (list order = auto-pick priority). CLI flags, fallback, and single-scene regen pick it up automatically. Video backends follow the same pattern in `pipeline/video/` (implement `submit`/`poll`/`download` too and batch animation comes free).

## Background music

Drop royalty-free mp3s into `music/<mood>/` — the assembler picks one matching the plan's mood and ducks it under the voiceover, or use `--music <file>` for a specific track. If you use CC-BY tracks (e.g. Kevin MacLeod / incompetech.com), credit the artist in the video description.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ffmpeg failed: ... No such filter: 'subtitles'` | Install `ffmpeg-full` (macOS) — plain Homebrew ffmpeg lacks libass |
| Images are colored gradients with text | No image key found — set `DASHSCOPE_API_KEY`, `OPENAI_API_KEY`, `PEXELS_API_KEY`, or `REPLICATE_API_TOKEN` |
| Character looks different in each scene | Define them in `characters` and reference by `{name}` — never describe them inline in scene prompts |
| Model keeps adding a trait ("no beard" gets a beard) | Use the scene's `negative_prompt`; if it persists, regenerate that scene with `--backend gpt-image-1` |
| `no voiceover for scene(s) ...` on assemble | Run `python -m pipeline.voiceover` first — assembly needs the audio for timing |
| `moderation_blocked` on an image | The fallback chain handles it; soften the prompt and `--scene N` to retry |
| Wan: `no video backend configured` | Set `DASHSCOPE_API_KEY`; free credit requires a Singapore-region Model Studio account |
| Stage re-runs do nothing (`pipeline.run`) | Stage already in `state.json` `done` list — remove it there |

## Not yet built

- YouTube upload (Data API + OAuth)
- Thumbnail generation
- True lip-sync (Wan s2v exists on DashScope but is paid per output second)
- 9:16 portrait mode for Shorts/Reels
- Scene transitions
