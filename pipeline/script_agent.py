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
"""


def generate_shot_plan(topic: str, model: str = "claude-haiku-4-5") -> ShotPlan:
    if model.startswith("gpt"):
        from openai import OpenAI

        client = OpenAI()  # reads OPENAI_API_KEY from env
        completion = client.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"Topic / rough script:\n\n{topic}"},
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
        messages=[{"role": "user", "content": f"Topic / rough script:\n\n{topic}"}],
        output_format=ShotPlan,
    )
    return response.parsed_output
