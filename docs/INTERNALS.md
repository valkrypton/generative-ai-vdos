# Internals — how each stage actually works

The README's "How it works" table tells you *what* each stage does. This document explains
the *mechanism* — what bytes go where — for developers extending the pipeline.

The connecting thread: stages just **write files into `output/<name>/`**; the next stage
reads whatever is there. No daemon, no queue, no database — the folder is the state.

## 1. Shot plan — structured LLM output (`pipeline/script_agent.py`)

Two messages go to the LLM: a **system prompt** (the rulebook — hook first, 4–8s scenes,
characters defined once, cinematographer-style image prompts, no negations) and a **user
message** (the topic, or an existing plan + feedback for `--change` / `--polish`).

The key mechanism is structured output:

```python
client.chat.completions.parse(
    model="gpt-4o-mini",
    messages=[...],
    response_format=ShotPlan,   # pydantic class from schema.py
)
```

The SDK converts `ShotPlan` into a JSON schema and the API **constrains generation to
match it** — the model cannot emit a missing field or wrong type. Pydantic validates the
reply into Python objects. The Anthropic branch does the same via `messages.parse` with
`output_format=ShotPlan`.

Character consistency is NOT delegated to the LLM (it provably fails at verbatim
repetition): scenes reference `{name}` placeholders, and `ShotPlan.expand()` substitutes
the full description at image/animation time, deterministically.

## 2. Images — diffusion via REST (`pipeline/images/qwen_image.py`)

Per scene, one prompt string is built: `style_prefix + ", " + expand(image_prompt)`.
One HTTPS POST:

```json
POST {DASHSCOPE_API_URL}/services/aigc/multimodal-generation/generation
{
  "model": "qwen-image-plus",
  "input": {"messages": [{"role": "user", "content": [{"text": "<prompt>"}]}]},
  "parameters": {
    "size": "1664*928",
    "prompt_extend": false,        // its rewriter kept adding rendered captions
    "negative_prompt": "text, words, ... [+ scene.negative_prompt]"
  }
}
```

The response carries a temporary URL (valid 24h); we download and `fit_cover()` crops
1664×928 → exactly 1920×1080. Diffusion models start from random noise and iteratively
denoise toward the text — same prompt, different image every run. That's also why
negated text fails ("no beard" puts *beard* in the conditioning) — true negatives go in
the `negative_prompt` parameter, which conditions *away* from those tokens.

Provider selection and the per-scene fallback chain live in `pipeline/images/__init__.py`;
every backend is a small class with `available()` + `generate()` (see `base.py`).

## 3. Animation — async task queue (`pipeline/video/wan.py`)

Video takes minutes, so the API is a job queue, not request/response:

1. **Submit** — POST the still (base64 data-URL in `input.img_url`) + motion prompt,
   header `X-DashScope-Async: enable`. Returns a `task_id` instantly.
2. **Poll** — GET `/tasks/{task_id}` every 15s: `PENDING → RUNNING → SUCCEEDED|FAILED`.
3. **Download** — success carries a `video_url` (valid 24h) → `video/scene_NN.mp4`.

Because submit is instant, `animate_scenes()` submits **all scenes first, then polls
them together** — Alibaba renders in parallel, so n clips ≈ wall-clock of 1. Wan treats
the still as frame 1 and generates ~120 coherent following frames guided by the motion
text. Everything is fail-soft: a failed/timed-out scene simply has no clip, and assembly
falls back to Ken Burns for it. Model/resolution/duration are constants
(`wan2.2-i2v-flash`, 720P, 5s) — a deliberate cost cap.

## 4. Voiceover — impersonating a browser (`pipeline/voiceover.py`)

There is **no API key because there is no official API**. Microsoft Edge has a free
built-in "Read Aloud" feature; the browser connects to a public websocket
(`wss://speech.platform.bing.com/...`) carrying only a token baked into Edge itself.
The `edge-tts` package sends byte-identical traffic — same endpoint, token, headers —
so the server treats it as the browser.

Over that websocket:

```
→  config: format=mp3, request word boundaries
→  SSML:   <voice name="ur-PK-UzmaNeural">ٹھیک ہے بیٹا...</voice>
←  binary chunks   (mp3 audio)          → appended to audio/scene_NN.mp3
←  WordBoundary    {offset, duration}   → saved to audio/scene_NN.words.json
```

The word timestamps are a synthesis byproduct — captions therefore cost nothing and
need no speech recognition. `Communicate(..., boundary="WordBoundary")` is required;
the default only emits sentence boundaries.

**Caveat:** this is unofficial. Microsoft could rotate the token or throttle non-Edge
traffic any time (the library has tracked such changes for years). If this becomes
production-critical, swap in Azure Speech (same voices, official, free 500k chars/month)
— stage isolation means only `voiceover.py` changes.

## 5. Assembly — four FFmpeg passes (`pipeline/assemble.py`)

All local, via `subprocess`:

1. **Per-scene clip** — `ffprobe` measures the scene mp3 (+0.3s breath). With an
   animation clip: `-stream_loop -1` loops it past the narration length, scale+crop to
   1080p, trim to exact duration, mux the mp3. Without: the Ken Burns effect —
   `zoompan` re-renders the still frame-by-frame with `zoom = 1 ± 0.001 × frame`,
   alternating direction per scene. **Audio length drives all timing.**
2. **Concat** — a list file + `ffmpeg -f concat -c copy` glues clips without re-encoding.
3. **Captions & overlays** — word timestamps grouped into ~4-word chunks → standard
   `.srt` → burned in with the `subtitles=` filter (requires libass, hence
   `ffmpeg-full` on macOS). `on_screen_text` is drawn top-center with `drawtext`.
4. **Music mix** — `[1:a]volume=0.12` + `amix` ducks the track under the voice;
   libx264 + aac encode `final.mp4`.

Gotcha encoded in the code: the final pass runs with `cwd=work_dir` so the subtitles
filter can use a relative filename, which means every *other* path argument must be
absolute (`.resolve()`).

## Cost map

| Stage | Service | Cost |
|---|---|---|
| Plan / revise / polish | gpt-4o-mini | ~$0.001 per call |
| Images | qwen-image-plus | free quota, then ~$0.02/image |
| Images (precision fallback) | gpt-image-1 | ~$0.01–0.02/image |
| Animation | wan2.2-i2v-flash 720P | free 1,650s trial, then ~$0.07–0.10 per 5s clip |
| Voice | edge-tts | $0 |
| Assembly | ffmpeg | $0 (local CPU) |
