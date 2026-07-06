# Composition track (Remotion)

Text/motion scenes — **title cards** and **quote cards** — rendered with React/Remotion
instead of AI image generation. A composition scene renders straight into
`output/<slug>/video/scene_NN.mp4`, the same slot the FFmpeg assembler already prefers
over a Ken Burns still, so nothing downstream changes. Cost: **$0** (local headless render).

## How it fits the pipeline

```text
plan → images → animate → voice → compose → assemble
                                   ^^^^^^^  (this)
```

A scene becomes composition-driven by setting `compose` instead of `media_prompt` in the
shot plan:

```json
{ "narration": "The two selves.",
  "compose": { "template": "title_card", "heading": "The Two Selves",
               "subheading": "a meditation on change" } }

{ "narration": "Yesterday I was clever...",
  "compose": { "template": "quote",
               "heading": "Yesterday I was clever, so I wanted to change the world.",
               "attribution": "Rumi" } }
```

- The `images` stage **skips** compose scenes (no image generated).
- The `compose` stage runs after `voice`, sizes each card to its narration length, themes
  it from the plan's `music_mood`, and renders to `video/scene_NN.mp4`.
- The `assemble` stage picks that clip up unchanged (concat, captions, music mix).

## Templates

| `template`    | Fields                            | Composition id | Use for |
|---------------|-----------------------------------|----------------|---------|
| `title_card`  | `heading`, `subheading?`          | `TitleCard`    | Opening title |
| `quote`       | `heading` (quote), `attribution?` | `Quote`        | Memorable line / quote video |
| `lower_third` | `heading` (name), `subheading?`   | `LowerThird`   | Introduce a person / place / term |
| `outro`       | `heading`, `subheading?` (CTA)    | `Outro`        | Closing card / call to action |

Palettes live in `src/theme.ts` (`MOOD_PALETTES`, mirrored in
`pipeline/compose/__init__.py`). 1920×1080 @ 30fps to match the assembler.
Typography is **Playfair Display**, baked in deterministically via
`@remotion/google-fonts` (see `src/fonts.ts`) — no render-time font flash.

## Setup & dev

```bash
cd remotion && npm install        # once
npm run studio                    # preview/edit templates live
python -m pipeline.compose output/<slug>   # re-render a plan's compose scenes
```

Requires Node.js ≥ 18 and FFmpeg (already a pipeline dependency).
