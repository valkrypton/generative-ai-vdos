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

print("ok")
