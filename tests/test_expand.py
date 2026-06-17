"""Plain-assert checks for ShotPlan.expand(). No framework — run with:

    python -m tests.test_expand
"""
from pipeline.schema import Character, Scene, ShotPlan


def expand(characters, prompt):
    plan = ShotPlan(
        title="t", description="d", tags=["x"], music_mood="calm",
        style_prefix="s", global_negative="g",
        characters=characters,
        scenes=[Scene(narration="n", image_prompt=prompt)],
    )
    return plan.expand(prompt)


octopus = [Character(name="octopus", description="a reddish-brown octopus")]
ali = [Character(name="ali", description="a young man with black hair")]

# A description containing the character's own name must not be re-scanned
# into "a reddish-brown the octopus" (regression: schema.py expand two-pass bug).
assert expand(octopus, "{octopus} swims") == "a reddish-brown octopus swims"

# First mention -> full description; later mentions -> short "the <name>" ref.
assert expand(ali, "{ali} hugs ali warmly") == "a young man with black hair hugs the ali warmly"

# "the {name}" must collapse the resulting double article ("the a ..." -> "a ...").
assert expand(ali, "the {ali} smiles") == "a young man with black hair smiles"

# --- outfit tests ---

boy = [Character(
    name="boy",
    description="a 6-year-old boy with messy brown hair, round face, big hazel eyes, wearing a white t-shirt and grey shorts",
    outfits={"superhero": "a 6-year-old boy with messy brown hair, round face, big hazel eyes, wearing a red Superman t-shirt and blue jeans"},
)]

# No outfit selected -> default description
assert expand(boy, "{boy} runs") == "a 6-year-old boy with messy brown hair, round face, big hazel eyes, wearing a white t-shirt and grey shorts runs"

def expand_outfit(characters, prompt, scene_outfit):
    plan = ShotPlan(
        title="t", description="d", tags=["x"], music_mood="calm",
        style_prefix="s", global_negative="g",
        characters=characters,
        scenes=[Scene(narration="n", image_prompt=prompt)],
    )
    return plan.expand(prompt, scene_outfit=scene_outfit)

# Outfit selected -> uses outfit description
assert expand_outfit(boy, "{boy} runs", {"boy": "superhero"}) == "a 6-year-old boy with messy brown hair, round face, big hazel eyes, wearing a red Superman t-shirt and blue jeans runs"

# Unknown outfit name -> falls back to default description
assert expand_outfit(boy, "{boy} runs", {"boy": "formal"}) == "a 6-year-old boy with messy brown hair, round face, big hazel eyes, wearing a white t-shirt and grey shorts runs"

# Character without outfits -> scene_outfit is ignored
assert expand_outfit(ali, "{ali} runs", {"ali": "superhero"}) == "a young man with black hair runs"

print("ok")
