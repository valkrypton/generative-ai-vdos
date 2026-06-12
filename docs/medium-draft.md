# I Built an AI Video Pipeline That Makes Narrated Videos for $0.001 Each

*Text prompt in → finished 1080p video out: AI scenes, real motion, multi-voice dialogue, word-synced captions. Open source, running almost entirely on free tiers.*

> **Insert image: `messi-ronaldo-cartoon.jpg`** (cover)

---

Last week I typed:

```bash
python -m pipeline.refine "Messi and Ronaldo chat about the World Cup with their friend Awais"
```

I reviewed the generated shot plan, asked for one change in plain English ("make Awais 48 and clean-shaven"), ran four more commands — and got a complete video: cartoon Messi and Ronaldo bantering in a stadium, three distinct voices, animated motion, burned-in captions, background music.

Total cost: **about a tenth of a cent.**

Premium AI video platforms charge $0.50–$5 *per clip* and are mostly browser-only. Free browser tools can't be scripted. I wanted a real pipeline — text in, video out, human review only where it matters. Here's the stack, and the five lessons I learned the hard way.

## The stack

| Stage | Tool | Cost |
|---|---|---|
| Idea → shot plan (JSON) | gpt-4o-mini, structured output | ~$0.001 |
| Images | Qwen (Alibaba Cloud) | **free quota** |
| Still → 5s motion clip | Wan 2.2 (same key) | **~1,650s free**, then ~$0.07/clip |
| Voice + word timestamps | edge-tts | $0 |
| Captions, editing, music | FFmpeg | $0, local |

The quiet hero is **Alibaba Cloud Model Studio**: one API key (sign up in the **Singapore region** — that's where the free tier lives) covers both a free image-generation quota for Qwen *and* ~1,650 seconds of free Wan video credit — roughly **35 fully-animated videos before you pay a cent**. After that, the cheapest tier is ~$0.07–0.10 per clip — still 10× under the premium platforms, through a real scriptable API.

## Architecture: a folder is the state machine

```
output/my-video/
  shot_plan.json        ← the contract every stage consumes
  images/scene_00.png
  video/scene_00.mp4    ← optional motion
  audio/scene_00.mp3    ← + scene_00.words.json (word timestamps)
  final.mp4
```

No framework, no queue, no database. Every stage reads and writes files; redoing one bad scene means deleting one file. The plan is a pydantic schema and the LLM is *forced* to match it (`response_format=ShotPlan`) — broken-JSON failures simply can't happen. A human review gate sits between the cheap step (the $0.001 plan) and the expensive ones.

## Lesson 1: LLMs can't repeat themselves — enforce consistency in code

My first videos had characters **changing clothes between scenes**. Each scene's image is generated independently — say "the girl" and the model invents a new girl every time.

Asking the LLM to repeat the full description verbatim in every scene **failed even when explicitly instructed** — it kept the face and dropped the clothes in 6 of 7 scenes. LLMs paraphrase; it's what they are.

The fix: characters are defined once, scenes say `{thief}`, and **code substitutes the full description deterministically**:

```json
"characters": [{"name": "thief", "description": "a mid-30s man with short black hair
  and stubble, wearing a black zip-up hoodie, dark blue jeans and white sneakers"}],
"scenes": [{"image_prompt": "{thief} crouching by the locker, picking the lock"}]
```

> **Insert image: `thief-consistency.jpg`** — same man, same outfit, three independently generated scenes

Need an *intentional* outfit change (pajamas → school uniform)? Define one entry per look with the same face: `{boy_home}`, `{boy_school}`. Drift becomes a choice, never an accident.

**If a model behavior matters, make it a code path, not a prompt instruction.**

## Lesson 2: image models draw your negations

I needed a clean-shaven character. "Clean-shaven" → beard. **"No beard, no mustache" → a fuller beard.** Diffusion models don't parse negation — the word "beard" becomes conditioning, and conditioning gets drawn.

The real mechanism is the **negative prompt parameter**, which steers generation *away* from tokens. And when even that loses to a model's prior, escalate that one image to a more instruction-following model — gpt-image-1 nailed it first try for $0.02.

> **Insert image: `awais-pair.jpg`** — finally clean-shaven, consistent across scenes

## Lesson 3: video APIs are job queues — submit all, then poll

A clip takes minutes to render, but *submitting* is instant and returns a task ID. So the pipeline submits **all scenes first, then polls them together** — nine clips finish in roughly the time of one. And it's fail-soft: a failed clip just means that scene stays a still with a Ken Burns zoom. One bad scene never kills a video.

## Lesson 4: the best TTS deal in tech is hiding in a browser

Microsoft Edge's free "Read Aloud" feature is backed by hundreds of neural voices, and the `edge-tts` package speaks the same websocket protocol the browser does — no key, no account. It streams back the audio **plus the millisecond each word is spoken**, which means perfectly synced captions with zero speech recognition. My favorite test: a mother-daughter dialogue **in Urdu**, two distinct voices, correct right-to-left captions.

> **Insert image: `urdu-captions.jpg`**

(It's unofficial and could break someday; the clean upgrade is Azure Speech — same voices, 500k free chars/month — and it would touch exactly one file.)

## Lesson 5: FFmpeg is the only video editor you need

Four local passes: per-scene clips (the motion clip looped and trimmed to the narration's exact length — **audio drives all timing**), concat, captions burned in via libass, and music ducked to 12% under the voice.

Music needs no AI but feels smart: the LLM picks a one-word `music_mood` per video, and the assembler grabs a matching track from `music/<mood>/`. Free sources: **YouTube Audio Library** (safest for monetized channels), **Pixabay** (no attribution), **Kevin MacLeod/incompetech** (CC-BY — credit him in the description, the most-forgotten obligation on YouTube). It's the biggest free quality upgrade in the pipeline.

macOS trap: Homebrew's default `ffmpeg` lacks libass — captions need `ffmpeg-full`.

## The bill

6-scene animated video: plan ~$0.003 + images $0 + clips $0 (free credit) + voice/captions/assembly $0 = **~$0.003**. After the free credits: under $0.50.

## Try it

**[github.com/awais786/generative-ai-vdos](https://github.com/awais786/generative-ai-vdos)**

```bash
git clone git@github.com:awais786/generative-ai-vdos.git && cd generative-ai-vdos
make install      # ffmpeg + venv + deps + .env template
make example      # renders a bundled example video — $0, no API keys needed
```

Add two keys (OpenAI + Alibaba Model Studio, Singapore region), then:

```bash
python -m pipeline.refine "your video idea"
python -m pipeline.images && python -m pipeline.video
python -m pipeline.voiceover && python -m pipeline.assemble
```

Backends are one-file plugins — if you find a better free image or video API, a PR would make my day.

---

*Every lesson above was learned from an actual failed video.*
