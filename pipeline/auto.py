"""One-shot: a prompt goes in, output/<slug>/final.mp4 comes out.

Runs every stage end to end with no review gate — plan + auto-polish +
consistency review (all refinements) -> images -> voiceover -> assemble.

    python -m pipeline.auto "a sparrow shares a giant berry with a hungry rabbit"

This is exactly `pipeline.run "..." --approve` with nothing to remember. It
uses the same free defaults (qwen images, no animation) and the same resumable
state.json, so re-running continues instead of re-billing. Extra flags pass
straight through, e.g.:

    python -m pipeline.auto "..." --name my-video --voice en-US-AriaNeural

For step-by-step review between stages, use pipeline.run (without --approve) or
the individual stage CLIs instead.
"""
import sys

from . import run


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(1 if len(sys.argv) < 2 else 0)
    # Reuse the resumable runner; just pre-approve the review gate.
    sys.argv = [sys.argv[0], sys.argv[1], "--approve", *sys.argv[2:]]
    run.main()


if __name__ == "__main__":
    main()
