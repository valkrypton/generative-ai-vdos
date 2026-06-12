# Examples

## The full flow — from your own prompt

```bash
# from the repo root, with .venv active and .env filled in:

# 1. Pass your idea as a prompt — generates + auto-polishes a reviewable plan
python -m pipeline.refine "a little sparrow finds a giant berry and shares it with a hungry rabbit, 3 scenes, kids story"

# 2. Review what it printed; iterate until happy (defaults to the latest video)
python -m pipeline.refine --change "make the rabbit grey instead of tan"

# 3. Generate, review images, then finish
python -m pipeline.images          # check output/<name>/images before continuing
python -m pipeline.video           # optional: animate (~5s credit/scene)
python -m pipeline.voiceover
python -m pipeline.assemble                          # music auto-picked from music/<mood>/
# or pass a specific track:
python -m pipeline.assemble --music ~/Downloads/my-track.mp3
open output/<name>/final.mp4
```

## No LLM key? Run the included plan

`the-sharing-berry/shot_plan.json` is the kind of plan step 1 produces, pre-written —
so steps 3–5 can be tested without any OpenAI/Anthropic key:

```bash
cp -r examples/the-sharing-berry output/
python -m pipeline.images   output/the-sharing-berry     # stills, one per scene
python -m pipeline.video    output/the-sharing-berry     # optional: animate (~5s credit/scene)
python -m pipeline.voiceover output/the-sharing-berry    # narrator + dialogue voices
python -m pipeline.assemble output/the-sharing-berry     # -> final.mp4
# with a specific music track instead of the mood-based pick:
python -m pipeline.assemble output/the-sharing-berry --music path/to/track.mp3
open output/the-sharing-berry/final.mp4
```

Skip `pipeline.video` if you don't have a DashScope key — scenes render as Ken Burns
stills and everything still works.

## Which API does each stage use?

| Stage | Command | Service | Env key (set in `.env`) | Without the key |
|---|---|---|---|---|
| Plan (skipped here — example plan is included) | `pipeline.refine` | OpenAI gpt-4o-mini or Anthropic Claude | `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` | required for *new* plans only |
| Images | `pipeline.images` | Qwen (Alibaba DashScope), or gpt-image-1 / Flux / Pexels | `DASHSCOPE_API_KEY` (or `OPENAI_API_KEY` / `REPLICATE_API_TOKEN` / `PEXELS_API_KEY`) | free gradient placeholders |
| Animate | `pipeline.video` | Wan i2v (Alibaba DashScope) | `DASHSCOPE_API_KEY` | stage skipped; stills + Ken Burns |
| Voiceover | `pipeline.voiceover` | Microsoft edge-tts | none — free, no key | always works (needs internet) |
| Assemble | `pipeline.assemble` | FFmpeg (local) | none — `brew install ffmpeg-full` | always works |

Get keys: copy `.env.example` to `.env` and follow the links in the main README's
**API keys** table. The recommended free setup is a single `DASHSCOPE_API_KEY`
([Alibaba Model Studio](https://modelstudio.console.alibabacloud.com), Singapore region —
free image quota + ~1,650s of video credit) plus one cheap LLM key for generating
your own plans.

## What this example demonstrates

- `characters` + `{pip}` / `{benny}` placeholders → the same look in every scene
- per-scene `voice` → narrator (scene 0) vs. two different dialogue voices (scenes 1–2)
- `motion` → talking characters instead of generic drift when animated
- `on_screen_text` → styled title overlays
- `negative_prompt` → keeping unwanted traits out of an image
