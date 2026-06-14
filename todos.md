# TODOs

## Image / character consistency

- [ ] **Local face-swap stage (`pipeline.faceswap`)** — optional, free, runs locally
      (no API call). Uses InsightFace + the `inswapper_128.onnx` model (~530MB) to
      swap one fixed reference face into every scene, so the face is pixel-identical
      across shots. Only fixes the **face** — not hair or clothing.
  - Deps are already in `requirements.txt` as commented-optional:
    `insightface`, `onnxruntime`, `opencv-python-headless`.
  - Model `inswapper_128.onnx` is **not** downloaded (official URL is dead;
    use a HuggingFace mirror, e.g. Gourieff/ReActor).
  - Stage itself is **not built** yet.
  - NOTE: probably redundant for the **qwen** and **openai** backends — they already
    keep face + hair + clothing consistent via the `edit()` reference-locking path.
    Mainly useful for backends that lack `edit()`.

- [ ] **Add `edit()` to the Flux backend** (`pipeline/images/flux.py`). It currently
      only implements `generate()` (plain text-to-image), so character consistency
      does NOT kick in on Flux — faces can drift between scenes.

## Motion (low-cost video architecture)

Goal: keep a 30s video at ~$0.05–0.20 by compositing stages instead of using a full
text-to-video model: Text → Scenes → Images → Motion → Audio → Final Render. Swap
models per stage to trade cost vs. quality. Stage-by-stage status:

| Stage | This project | Status |
|---|---|---|
| Script (LLM) | `pipeline.refine` (openai/litellm/anthropic) | DONE (~$0.001) |
| Images | `pipeline.images` — qwen (free) / flux schnell (~$0.003) / openai | DONE |
| Motion | see below | partly done |
| Audio | `pipeline.voiceover` — edge-tts (free) | DONE |
| Render | `pipeline.assemble` — ffmpeg | DONE (free) |

Motion options:

- [x] **Ken Burns (zoom/pan) — ALREADY BUILT, free, no model.** Lives in
      `pipeline/assemble.py` (`_KB_MODES`, 6 patterns: zoom in/out, pan L↔R, corner
      zooms) applied via ffmpeg `zoompan` with fades. Runs automatically for any scene
      without a paid animated clip. This is the spec's "Option B" ultra-cheap fallback.
      It lives in `assemble` (not a separate stage) on purpose: Ken Burns must match
      each scene's narration length, which is only known after voiceover. => a 30s
      video currently costs ~$0.02 all-in (LLM + images + free TTS + free motion).
- [ ] **Generative motion (people actually move)** — `pipeline.video` (Wan i2v),
      DISABLED by default because it spends DashScope credit. Spec's "Option A".
- [ ] **Parallax depth animation (2.5D)** — free at runtime BUT needs a depth model
      download (MiDaS / Depth-Anything, hundreds of MB). Not built; conflicts with the
      "no heavy local models" preference (same reason face-swap was paused).
- [ ] **Frame interpolation (RIFE)** — needs the RIFE model download. Not built.
- [ ] (optional, free) Improve the existing Ken Burns: more pattern variety, gentler
      easing, optionally bias pan direction from the scene's `motion` text hint.

Target cost bands (from the spec): low-cost $0.05–0.13 · balanced $0.12–0.20 ·
premium (some generative motion) $0.20–0.50 per 30s video.

## Housekeeping

- [ ] **Commit the agnostic-model refactor** (uncommitted): `qwen_image.py`,
      `gpt_image.py`, `flux.py`, `images/__init__.py`, `.env.example`,
      `requirements.txt`. All model ids now come from `.env`; nothing hardcoded.
