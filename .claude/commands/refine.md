---
description: Refine a rough video idea into a reviewable shot plan draft (no files written until approved)
argument-hint: <rough idea, story, or dialogue text>
---

The user gave this rough video idea:

$ARGUMENTS

Refine it into a draft shot plan for the video pipeline in this repo, and present it for review. Do NOT write any files and do NOT run any pipeline stages yet — this step is for verification only.

Present the draft in readable form (not raw JSON):

1. **Title** + one-line summary, and total estimated length (scenes × ~5s).
2. **Characters** — if any person/animal appears in more than one scene, define ONE exact description (age, hair, clothing with specific colors, species) that will repeat VERBATIM in every scene's image prompt. Show these up front so the user can adjust outfits/looks.
3. **Scenes** — numbered list; for each:
   - narration (in the language the user implied — e.g. Urdu if the dialogue is Urdu)
   - image: what the picture shows (using the verbatim character descriptions)
   - motion: what moves (if a character speaks this line: "lips moving as she speaks, gesturing")
   - voice: per-scene edge-tts voice for dialogue (ur-PK-UzmaNeural, ur-IN-GulNeural, ur-PK-AsadNeural for Urdu; en-US-JennyNeural / en-US-AndrewNeural etc. for English); null for single-narrator videos
4. **Style prefix** (one consistent visual style) and **music mood** (calm / upbeat / chill / dramatic / mysterious / inspiring).
5. **Open questions** — anything ambiguous in the user's text (ages, setting, language, number of scenes).

Then ask the user what to change. Iterate on their feedback, re-presenting only the changed parts. Costs nothing until generation starts.

Only after the user explicitly approves: write `output/<short-kebab-name>/shot_plan.json` matching `pipeline/schema.py` (fields: title, description, tags, music_mood, style_prefix, scenes[narration, image_prompt, on_screen_text, voice, motion]), then show the stage commands:

```
python -m pipeline.images output/<name>     # review images before continuing
python -m pipeline.video output/<name>      # ~5s credit per scene
python -m pipeline.voiceover output/<name>
python -m pipeline.assemble output/<name>
```

and offer to run them stage by stage (pausing after images for review).
