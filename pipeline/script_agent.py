"""Stage 1: topic -> refined script -> shot plan JSON (one LLM call).

Provider is picked by the model name: "claude-*" uses Anthropic (ANTHROPIC_API_KEY),
"gpt-*" uses OpenAI (OPENAI_API_KEY).
"""
from .schema import ShotPlan

SYSTEM = """You are a scriptwriter for a faceless YouTube channel. Given a topic or rough
script, produce a complete shot plan for a 60-90 second video built from still images,
voiceover, and captions.

Rules:
- The first scene's narration must hook the viewer in one sentence — open with a question,
  a surprising fact, or a bold claim. Never open with "Welcome" or "In this video".
- Keep narration conversational and punchy. Short sentences. No filler.
- Each scene's narration should take roughly 4-8 seconds to speak aloud.
- The final scene is a clear call to action (subscribe / comment prompt), one sentence.
- image_prompt must describe a concrete visual, never abstract concepts. Do not ask for
  rendered text in images — text belongs in on_screen_text.
- Pick one consistent style_prefix and write every image_prompt to work with it.

Character consistency (critical — scenes are generated independently):
- If a person or animal character appears in more than one scene, invent ONE exact
  description (age, hair, clothing with specific colors, species/breed) and repeat it
  VERBATIM in every image_prompt where they appear. Example: write "the 10-year-old girl
  in a pink frock with white flowers" in scene 1 AND scene 4 — never "the girl" or a
  reworded version. Drifting descriptions produce a different-looking character per scene.

Motion (each still may be animated into a video clip):
- Set the motion field to describe what should move in the scene. If a character is
  speaking the narration, say so explicitly: "the girl is talking, lips moving as she
  speaks, gesturing". For scenery use camera/ambient motion: "slow drift, leaves swaying".

Dialogue and voices:
- For narrator-style videos leave voice null everywhere (one narrator voice is used).
- If scenes are spoken BY different characters (dialogue), set voice per scene to a
  fitting edge-tts voice and write the narration as that character's spoken line.
  Examples: en-US-AndrewNeural / en-US-BrianNeural (male), en-US-JennyNeural /
  en-GB-SoniaNeural (female), ur-PK-UzmaNeural / ur-IN-GulNeural (Urdu female),
  ur-PK-AsadNeural (Urdu male), hi-IN-SwaraNeural (Hindi female).
- Match the voice language to the narration language.
"""


def _parse_with_llm(user_content: str, model: str) -> ShotPlan:
    if model.startswith("gpt"):
        from openai import OpenAI

        client = OpenAI()  # reads OPENAI_API_KEY from env
        completion = client.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": user_content},
            ],
            response_format=ShotPlan,
        )
        return completion.choices[0].message.parsed

    import anthropic

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    response = client.messages.parse(
        model=model,
        max_tokens=8192,
        system=SYSTEM,
        messages=[{"role": "user", "content": user_content}],
        output_format=ShotPlan,
    )
    return response.parsed_output


def generate_shot_plan(topic: str, model: str = "claude-haiku-4-5") -> ShotPlan:
    return _parse_with_llm(f"Topic / rough script:\n\n{topic}", model)


def revise_shot_plan(plan: ShotPlan, feedback: str, model: str = "claude-haiku-4-5") -> ShotPlan:
    return _parse_with_llm(
        "Here is an existing shot plan JSON:\n\n"
        f"{plan.model_dump_json(indent=2)}\n\n"
        "Apply the following feedback and return the COMPLETE updated shot plan. "
        "Change only what the feedback requires and keep everything else identical. "
        "If the feedback changes a character's look, update that character's "
        "description verbatim in every scene where they appear:\n\n"
        f"{feedback}",
        model,
    )
