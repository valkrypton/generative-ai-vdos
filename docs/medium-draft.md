# I Built an AI Video Pipeline That Makes Narrated Videos for $0.001 Each

(Final version as published on Medium — see git history for earlier drafts.)

Text prompt in → Finished 1080p video out → Human review only where it actually matters

Last week I typed:

    python -m pipeline.refine "Messi and Ronaldo chat about the World Cup with their Pakistani friend"

I reviewed the generated shot plan, made one change in plain English: "Set the friend's age to 48 and make him clean-shaven." Then I ran four more commands and got a complete video: cartoon Messi and Ronaldo bantering in a stadium with their Pakistani friend, three distinct voices, animated motion, burned-in captions, and background music.

The total cost? About a tenth of a cent.

[... full text as published — maintained on Medium; this file records the final structure:
 The Stack / Architecture: a folder is the state machine /
 Lesson 1: LLMs can't reliably repeat themselves — enforce consistency in code /
 Lesson 2: Image models draw your negations /
 Lesson 3: Video APIs are job queues — submit all, then poll /
 Lesson 4: The best TTS deal in tech is hiding in a browser /
 Lesson 5: FFmpeg is the only video editor you need /
 The bill / Try it]
