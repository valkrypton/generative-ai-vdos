# I Built an AI Video Pipeline That Makes Narrated Videos for $0.001 Each — Here's What I Learned

*One text prompt → a finished 1080p video with AI scenes, real motion, multi-voice dialogue in any language, and word-synced captions. Open source, and it runs almost entirely on free tiers.*

> **Insert image: `messi-ronaldo-cartoon.jpg`** — cartoon Messi & Ronaldo chatting in a stadium (use as the cover image)

---

Last week I typed this into my terminal:

```bash
python -m pipeline.refine "Messi and Ronaldo chat about the World Cup with their friend Awais"
```

A minute later I was reading a generated shot plan — six scenes, dialogue lines, camera directions, a voice assigned to each character. I asked for one change in plain English ("make Awais 48 and clean-shaven"). Then four more commands, and out came a complete video: cartoon Messi and Ronaldo bantering in a stadium, my self-insert cheering in a Pakistani-flag shirt, three distinct voices, animated motion, burned-in captions, background music.

The bill for all of it: **about a tenth of a cent.**

That number is not a trick. It's what becomes possible when you connect the right free tiers with ~1,400 lines of Python and let a folder full of files be your orchestration framework. This article walks through how it works — and the five lessons about generative AI APIs I learned the hard way, so you don't have to.

## The problem with "AI video" in 2026

If you want automated video today, your options look like this:

- **Premium platforms** (Runway, Kling, Veo via Flow): beautiful output at **$0.50–$5 per clip** — a 10-scene daily video habit costs more than a salary. And most are browser-only: no API, no automation.
- **Free browser tools** (Qwen chat, Meta AI, AI Studio): genuinely free, genuinely good — and genuinely manual. Download each image by hand, every day? You've built yourself a job.

I wanted the third thing: **a real pipeline.** Text in, video out, every step scriptable, humans reviewing only where judgment matters, and a marginal cost near zero.

## The stack that worked

| Stage | Tool | Cost |
|---|---|---|
| Idea → shot plan (JSON) | gpt-4o-mini, structured output | ~$0.001 |
| Images | Qwen (Alibaba Cloud) | **free quota** |
| Animation: still → 5s motion clip | Wan 2.2 (same key!) | **~1,650s free**, then ~$0.07/clip |
| Voiceover + word timestamps | edge-tts | $0 |
| Captions, editing, music | FFmpeg | $0, local |

### The deal that makes this possible

The quiet hero is **Alibaba Cloud Model Studio**. One API key (sign up in the **Singapore region** — that's where the free tier lives) currently gets a new account:

- a **free image-generation quota** for the Qwen image models — high quality, native 16:9, and the best text-rendering of any model I tested, and
- **~1,650 seconds of free video generation credit** (90 days) for the Wan image-to-video models — that's ~330 motion clips, enough for **about 35 fully-animated videos** before you pay a cent.

After the trial, Wan's cheapest tier runs roughly $0.07–0.10 per 5-second clip — still an order of magnitude under the premium platforms. I had dismissed "free AI" as browser-toy territory until I found this; it's a real, scriptable API with an async job queue, and it's the reason the whole pipeline stays effectively free.

## Architecture: the folder is the state machine

```
output/my-video/
  shot_plan.json        ← the contract every stage consumes
  images/scene_00.png   ← stage 2
  video/scene_00.mp4    ← stage 2.5 (optional motion)
  audio/scene_00.mp3    ← stage 3 (+ scene_00.words.json — word timestamps)
  final.mp4             ← stage 4
```

No orchestration framework, no queue, no database. Every stage reads files and writes files. Resume after a crash = look at what exists. Redo one bad scene = delete one file. Swap an image provider = nothing else notices.

Two design choices carry the whole thing:

1. **The shot plan is a pydantic schema, and the LLM physically cannot violate it.** `response_format=ShotPlan` makes the API constrain generation to the schema — there is no "model returned broken JSON" failure mode, ever.
2. **A human review gate sits between cheap and expensive.** The plan costs $0.001; the assets cost real quota. You read the plan, fix it in plain English (`--change "make the rabbit grey"`), and only then generate.

Now, the lessons.

## Lesson 1: LLMs cannot repeat themselves — enforce consistency in code

My first videos had an embarrassing flaw: **characters changed clothes between scenes.** Pink frock in scene 1, yellow dress in scene 3, same girl.

The cause is structural: every scene's image is generated independently — the image model never sees the other scenes. If a prompt says "the girl", the model invents a new girl.

The obvious fix — instruct the LLM to repeat each character's full description verbatim in every scene — **failed, repeatedly.** Even when I explicitly asked it to paste "a mid-30s man wearing a black zip-up hoodie, dark blue jeans and white sneakers" into all seven scenes, it kept the face and silently dropped the clothing in six of them. LLMs paraphrase. It is what they are.

What worked: stop trusting the model with repetition.

```json
"characters": [
  {"name": "thief", "description": "a mid-30s man with short black hair and stubble,
    wearing a black zip-up hoodie, dark blue jeans and white sneakers"}
],
"scenes": [
  {"image_prompt": "{thief} crouching by the locker, picking the lock"}
]
```

The LLM writes `{thief}`; **code substitutes the full description into every scene deterministically.** Consistency went from a hope to a guarantee:

> **Insert image: `thief-consistency.jpg`** — the same man, same outfit, across three independently-generated scenes

**The principle: if a model behavior matters, make it a code path, not a prompt instruction.**

And when the story *wants* a change — the boy wears pajamas at home but a uniform at school —
you don't fight the system, you use it: define one character entry **per look**, sharing the
same face and hair:

```json
"characters": [
  {"name": "boy_home",   "description": "an 8-year-old boy with short brown hair and freckles, wearing blue striped pajamas"},
  {"name": "boy_school", "description": "an 8-year-old boy with short brown hair and freckles, wearing a navy school uniform with a red tie"}
]
```

Morning scenes reference `{boy_home}`, school scenes `{boy_school}` — the face stays
identical because that part of the text is identical, and the outfit changes exactly when
you say so. Same trick for location changes: keep the setting description in the scene
prompts as consistent (or as varied) as the story needs — drift is always a choice, never
an accident.

## Lesson 2: image models draw your negations

I needed a clean-shaven character. The sequence of failures:

1. Prompt: "clean-shaven" → beard.
2. Prompt: "no beard, no mustache" → a **fuller** beard.
3. Prompt: "completely smooth bare shaved face" → beard, now grey.

Diffusion models don't parse negation. The tokens "beard" and "mustache" become conditioning, and the model draws what it's conditioned on. The actual mechanism for exclusion is the **negative prompt parameter** — a separate field that steers generation *away* from tokens.

And when even that loses to a model's prior (Qwen is deeply convinced middle-aged Pakistani men have beards), the escalation is a more instruction-following model for that one image. gpt-image-1 got it right on the first try, for two cents.

> **Insert image: `awais-pair.jpg`** — finally clean-shaven, consistent across both his scenes

My schema now has `negative_prompt` per scene, and the fix for a stubborn image is one flag: `--scene 4 --backend gpt-image-1`.

## Lesson 3: video APIs are job queues — submit everything, then poll

A motion clip takes minutes to render. Sequentially, a 9-scene video would take an hour of waiting. But these APIs are async: submission is instant and returns a task ID.

So the animation stage **submits all scenes first, then polls them together** — the provider renders in parallel, and nine clips finish in roughly the time of one. It's also fail-soft: a clip that errors or times out simply doesn't exist, and the assembler falls back to a Ken Burns zoom on that scene's still. One bad scene never kills a video.

## Lesson 4: the best TTS deal in tech is hiding in a browser

Microsoft Edge ships a free "Read Aloud" feature backed by hundreds of neural voices. The `edge-tts` package speaks the same websocket protocol the browser uses — no key, no account, no quota I've ever hit.

Down that websocket come two streams: the audio, and **WordBoundary events** — the millisecond each word is spoken. That second stream means perfectly synced subtitles with no Whisper pass and no cost. It handles languages beautifully too: one of my test videos is a mother-daughter conversation **in Urdu, with two distinct female voices and correctly rendered right-to-left captions.**

> **Insert image: `urdu-captions.jpg`** — Urdu dialogue, per-character voices, burned-in RTL captions

(Honest caveat: it's an unofficial API and could break someday. The clean upgrade is Azure Speech — same voices, official, 500k free chars/month — and stage isolation means that's a one-file change.)

## Lesson 5: FFmpeg is the only video editor you need

The last stage is four local FFmpeg passes:

1. **Per-scene clips** — the motion clip looped and trimmed to the narration's exact length (**audio drives all timing** — pacing always matches speech), or a `zoompan` Ken Burns effect when there's no clip.
2. **Concat** — glue scenes without re-encoding.
3. **Captions** — word timestamps → 4-word SRT chunks → burned in via libass; scene titles via `drawtext`.
4. **Music** — ducked to 12% under the voice with `amix`, encode, done.

One trap for macOS users: Homebrew's default `ffmpeg` is built **without libass** — the subtitles filter literally doesn't exist. You want `ffmpeg-full`.

### Background music: free, and smarter than you'd expect

Music needs no AI at all, but a small design choice makes it feel intelligent: the shot-plan
LLM picks a one-word `music_mood` for every video (calm, upbeat, dramatic, chill...), and the
assembler grabs a random track from the matching `music/<mood>/` folder — so a kids' story
automatically gets gentle piano while a heist video gets tension. Want a specific track for
one video? `--music path/to/track.mp3` overrides everything.

Where to get tracks legally for $0:

- **YouTube Audio Library** (in YouTube Studio) — the safest for monetized channels; most
  tracks need no attribution and carry zero copyright-claim risk.
- **Pixabay Music** — free for commercial use, no attribution.
- **Kevin MacLeod / incompetech.com** — a legendary catalog of ~2,000 tracks under CC-BY:
  free for anything, but you **must credit him in the video description**. Forgetting
  attribution on CC-BY music is the most common licensing mistake on YouTube — put the
  credit line in a file next to the tracks so you never lose it.

The mix itself is one FFmpeg filter: loop the track for the video's length, drop it to 12%
volume so it never fights the narration, `amix` the two streams, end with the video. Ten
lines of arguments, zero dollars, and the difference between "TTS demo" and "watchable video"
is bigger than any other free upgrade in the pipeline.

> **Insert image: `space-friends.jpg`** — the pipeline does photorealistic styles too: a space-facts reel, fully animated

## What a video actually costs

A 6-scene, ~35 second animated video:

| Item | Cost |
|---|---|
| Shot plan + 2 revisions | ~$0.003 |
| 6 images (Qwen) | $0 |
| 6 motion clips (Wan) | $0 on free credit (later ~$0.45) |
| 2-voice dialogue + captions | $0 |
| Assembly + music | $0 |
| **Total** | **~$0.003 — later, under $0.50** |

## Try it yourself

Everything is open source: **[github.com/awais786/generative-ai-vdos](https://github.com/awais786/generative-ai-vdos)**

```bash
git clone git@github.com:awais786/generative-ai-vdos.git
cd generative-ai-vdos
make install      # ffmpeg + venv + dependencies + .env template
make example      # renders a bundled example video — $0, no API keys needed
```

Then add two keys — OpenAI (plans, ~$0.001 each) and [Alibaba Cloud Model Studio](https://modelstudio.console.alibabacloud.com) (images + animation, Singapore region for the free tier) — and:

```bash
python -m pipeline.refine "your video idea"     # review & iterate on the plan
python -m pipeline.images                       # inspect before spending credit
python -m pipeline.video                        # animate
python -m pipeline.voiceover && python -m pipeline.assemble
```

The provider system makes new backends a one-file change — if you find a better free image or video API, a PR would make my day.

---

*Built with Claude Code over a few evenings of generating, breaking, and fixing — every lesson above was learned from an actual failed video.*
