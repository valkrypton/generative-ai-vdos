# Examples

Ready-to-run shot plans — no LLM call needed, so they work even without an OpenAI/Anthropic key.

## Run "The Sharing Berry"

```bash
# from the repo root, with .venv active and .env filled in:
cp -r examples/the-sharing-berry output/
python -m pipeline.images   output/the-sharing-berry     # stills, one per scene
python -m pipeline.video    output/the-sharing-berry     # optional: animate (~5s credit/scene)
python -m pipeline.voiceover output/the-sharing-berry    # narrator + dialogue voices
python -m pipeline.assemble output/the-sharing-berry     # -> final.mp4
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
