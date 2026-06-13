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

**Cost per video:** ~$0.001 (script) + $0 images (Qwen free quota) + $0 voice — or **$0 end-to-end in placeholder mode**. Optional animation: free trial credit, then ~$0.07–0.10 per 5s clip at our settings (wan2.2-i2v-flash, 720P; pricier Wan tiers go up to ~$0.25 — exact rates in the Model Studio console).

## Features

- **Refine-and-iterate workflow** — rough text in, reviewable shot plan out; revise it with plain-English feedback before anything is generated.
- **Consistent characters** — define each recurring character once; the pipeline substitutes the full description into every scene's prompts (code-enforced, not LLM-hoped).
- **Auto-polish and consistency review** — every new plan goes through two automatic LLM passes: image prompt polish (adds shot type, lighting, mood) and consistency review (catches missing placeholders, wrong negatives, animate cap violations). No extra flags needed.
- **Character negative prompts** — set a `negative` field on any character to suppress traits the model keeps adding (bald character: `"hair, wig"`; white hair: `"dark hair, black hair"`). Merged automatically into every scene that character appears in.
- **Global negative** — one `global_negative` field on the shot plan blocks unwanted traits from the entire video (e.g. `"woman, female"` for a male-only video).
- **Multi-provider with fallback** — 5 image backends, auto-picked by available keys; a failed scene falls through to the next backend instead of killing the run.
- **Real motion (optional, disabled by default)** — stills animated into video clips (Wan i2v); failed scenes gracefully stay as Ken Burns stills. Animation is currently disabled — requires uncommenting code in `pipeline/video/__main__.py`.
- **6-direction Ken Burns** — zoom-in, zoom-out, pan left→right, pan right→left, zoom top-left, zoom bottom-right; varies per scene automatically with per-clip fade transitions.
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
make install           # installs ffmpeg + python venv + dependencies, creates .env
# then put your keys in .env and: source .venv/bin/activate

make example           # optional: render the bundled example video, $0, no keys needed
```

<details>
<summary>Manual setup (what `make install` does)</summary>

```bash
brew install ffmpeg-full && brew link --overwrite ffmpeg-full   # macOS
# sudo apt install ffmpeg                                       # Linux

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # then edit it and add your keys
# (the pipeline auto-loads .env — no manual sourcing needed)
```

</details>

### API keys

| Key | Used for | Where to get it | Cost |
|---|---|---|---|
| `OPENAI_API_KEY` | Shot plan (gpt-4o-mini) + images (gpt-image-1, never auto-selected — requires explicit `--backend gpt-image-1`) | [platform.openai.com](https://platform.openai.com/api-keys) | ~$0.001/plan, ~$0.01–0.02/image |
| `ANTHROPIC_API_KEY` | Shot plan (Claude) — alternative to OpenAI | [console.anthropic.com](https://console.anthropic.com/) | ~$0.001/plan |
| `DASHSCOPE_API_KEY` | Images (`qwen-image`, free quota, always tried first) + animation (Wan i2v) | [Alibaba Model Studio](https://modelstudio.console.alibabacloud.com) — **pick the Singapore region**; new accounts get free image quota and ~1,650s of video credit (90 days) | free quota, then ~$0.02/image, ~$0.07–0.10/clip |
| `REPLICATE_API_TOKEN` | Images via Flux Schnell (free tier, tried second; also `pip install replicate`) | [replicate.com](https://replicate.com/) | ~$0.003/image |
| `PEXELS_API_KEY` | Free stock photos instead of AI images | [pexels.com/api](https://www.pexels.com/api/) | free |

Minimum: one LLM key (OpenAI or Anthropic). With no image key the pipeline renders gradient placeholders so the whole flow can be tested for $0.

## Workflow

**Try it without writing anything:** a ready-made plan ships in [`examples/`](examples/README.md) —
`cp -r examples/the-sharing-berry output/ && python -m pipeline.images output/the-sharing-berry`
(see `examples/README.md` for the full run and which API key each stage needs).

### Step 1 — refine: rough idea → reviewable plan

```bash
python -m pipeline.refine "Messi and Ronaldo chat about the World Cup with their friend Awais. 4-6 scenes, three distinct male English voices."
```

Prints the full plan — title, character cards, every scene's narration / expanded image prompt / motion / voice — and writes it to `output/<title-slug>/shot_plan.json`. Costs ~$0.001, generates nothing else yet.

Polish and consistency review run automatically — no `--polish` needed for new plans.

Iterate until it's right (each command defaults to the most recent video):

```bash
python -m pipeline.refine --change "make Awais 48 and clean-shaven, put him in the stadium"
python -m pipeline.refine --polish             # rewrite image prompts with shot/lighting detail (manual, for existing plans)
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
# Animation is currently DISABLED (to avoid accidental DashScope charges).
# To re-enable: open pipeline/video/__main__.py and uncomment the code block.
# python -m pipeline.video

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

## How it works — what each stage actually does

Each stage writes files into the video's folder (`output/<name>/`); the next stage reads
them. Nothing is hidden — every intermediate artifact can be opened and inspected.

| Stage | Tool | Input → Output | What happens |
|---|---|---|---|
| 1. Shot plan | gpt-4o-mini (or Claude) | rough text → `shot_plan.json` | An LLM breaks the idea into scenes: narration line, image description, motion, voice per scene. This JSON is the single source of truth for everything downstream. ~$0.001. |
| 2. Images | Qwen / Flux / Pexels / gpt-image-1 | prompts → `images/scene_NN.png` | For each scene, `style_prefix + image_prompt` (with `{character}` placeholders expanded) goes to an image AI, which paints one still frame. Three-layer negative merging: global_negative + character negatives + scene.negative_prompt. Free on Qwen quota. |
| 2.5 Animate | Wan (DashScope) — **DISABLED by default** | still + motion text → `video/scene_NN.mp4` | Wan keeps the people/background from the still and imagines the next ~5 seconds of movement, frame by frame. The costly step — review images first. A failed scene just stays a still. To enable: uncomment `pipeline/video/__main__.py`. |
| 3. Voiceover | edge-tts (free) | narration → `audio/scene_NN.mp3` + `.words.json` | Microsoft TTS speaks each line in the scene's voice, and streams back the millisecond each word is spoken — that's how subtitles sync perfectly without any speech recognition. |
| 4. Music | none (just a file) | `music/<mood>/*.mp3` | A track matching the plan's mood is picked (or `--music <file>`); it's mixed in during assembly. |
| 5. Assemble | FFmpeg | everything above → `final.mp4` | The robot video editor: see below. |

FFmpeg does four jobs in sequence:

1. **Per-scene clip** — take the scene's Wan clip (looped if narration runs past 5s; or a
   Ken Burns effect over the still if there's no clip — 6 directions: zoom-in, zoom-out,
   pan left→right, pan right→left, zoom top-left, zoom bottom-right, with per-clip fade
   transitions), attach the scene's mp3, and trim to exactly the narration length + 0.3s.
   The audio drives all timing — pacing always matches the speech.
2. **Concatenate** — glue the scene clips back-to-back.
3. **Captions** — convert the word timestamps into ~4-word subtitle chunks burned onto the
   pixels, plus `on_screen_text` titles drawn at the top.
4. **Music mix** — layer the track under the voices at 12% volume and encode `final.mp4`.

```
text ──LLM──▶ plan ──image AI──▶ stills ──Wan──▶ moving clips
plan ──TTS──▶ speech + word timings
ffmpeg: (clips + speech) per scene → glue → burn subtitles → mix music → final.mp4
```

Because every stage only reads files, any stage can be re-run, swapped (Qwen ↔
gpt-image-1), or fixed for a single scene without touching the rest.

For the deeper mechanics — structured LLM output, the diffusion REST calls, Wan's async
task queue, how edge-tts works without a key, and FFmpeg's four passes — see
[docs/INTERNALS.md](docs/INTERNALS.md).

## The shot plan format

`shot_plan.json` is the contract every stage consumes. The important fields:

```jsonc
{
  "title": "...", "description": "...", "tags": [...],
  "music_mood": "calm | upbeat | chill | dramatic | mysterious | inspiring",
  "style_prefix": "vibrant 3D cartoon animation style, ...",   // prepended to every image prompt
  "global_negative": "changing hairstyle, inconsistent clothing, different face, extra limbs, text, watermark, blurry",  // NEW: applied to every scene
  "characters": [
    { "name": "thief",
      "description": "a mid-30s man with short black hair and stubble, wearing a black zip-up hoodie, dark blue jeans and white sneakers",
      "negative": "beard, mustache, different person"  // NEW: merged into every scene this character appears in
    }
  ],
  "scenes": [
    {
      "narration": "What would you do if the cops were closing in?",   // the spoken line
      "image_prompt": "{thief} crouching by the locker, picking the lock",
      "motion": "{thief} is talking, lips moving as he speaks",         // optional, drives animation
      "voice": "en-US-BrianNeural",          // optional, per-scene speaker (dialogue)
      "on_screen_text": "Caught!",           // optional, styled title overlay
      "negative_prompt": "beard, mustache",  // optional, scene-level things the image must NOT contain
      "reference_image": "refs/office.jpg",  // optional, build the scene on a real photo (gpt-image-1)
      "animate": false                       // NEW: true = real motion clip (max 2 per video, DISABLED by default); false = Ken Burns
    }
  ]
}
```

**Character consistency:** scenes are generated independently, so the pipeline substitutes each character's full description wherever `{name}` (or the bare name) appears in `image_prompt`/`motion`. Change a character's look in one place; every scene follows.

**Intentional outfit/scene changes:** define one character entry per look with the same face/hair — e.g. `boy_home` ("…wearing blue striped pajamas") and `boy_school` ("…wearing a navy school uniform") — and reference the right one per scene. Drift is a choice, never an accident.

**Negatives — three layers merged automatically:**
1. `global_negative` on `ShotPlan` — blocks traits from every scene in the video.
2. `Character.negative` — blocks traits from every scene that character appears in.
3. `Scene.negative_prompt` — scene-specific overrides.

Image models ignore negated text — "no beard" *draws a beard*. Always use the negative fields instead.

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
  video/           Stage 2.5 (optional, DISABLED by default): image-to-video
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
| Model keeps adding a trait ("no beard" gets a beard) | Use the scene's `negative_prompt`; for persistent per-character traits use `Character.negative` — it's merged into every scene automatically |
| Lady/woman appears in a male-only video | Add `"woman, female, lady"` to `global_negative` in `shot_plan.json` |
| Character trait keeps appearing despite `negative_prompt` | Add it to the `Character.negative` field — it's merged into every scene automatically |
| `pipeline.video` does nothing | Animation is disabled by default. Open `pipeline/video/__main__.py` and uncomment the code block to re-enable. |
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
