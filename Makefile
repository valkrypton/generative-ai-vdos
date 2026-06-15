UNAME := $(shell uname)
VENV  := .venv
PY    := $(VENV)/bin/python

.PHONY: help install sync ffmpeg env example clean-example

help:
	@echo "make install        - full setup: ffmpeg + dependencies + .env"
	@echo "make sync           - install/update Python dependencies via uv"
	@echo "make example        - run the bundled example end-to-end (free, no keys needed)"
	@echo "make clean-example  - remove the example's generated output"

install: ffmpeg sync env
	@echo ""
	@echo "Setup complete. Next:"
	@echo "  1. put your keys in .env (OPENAI_API_KEY, DASHSCOPE_API_KEY)"
	@echo "  2. source $(VENV)/bin/activate"
	@echo "  3. python -m pipeline.refine \"your video idea\""

sync: pyproject.toml
	uv sync

$(VENV): pyproject.toml
	uv sync

ffmpeg:
ifeq ($(UNAME),Darwin)
	@if ffmpeg -filters 2>/dev/null | grep -q subtitles; then \
		echo "ffmpeg with libass: OK"; \
	else \
		echo "installing ffmpeg-full (plain ffmpeg lacks libass for captions)..."; \
		brew install ffmpeg-full && brew link --overwrite ffmpeg-full; \
	fi
else
	@if command -v ffmpeg >/dev/null 2>&1; then \
		echo "ffmpeg: OK"; \
	else \
		echo "installing ffmpeg..."; \
		sudo apt-get update && sudo apt-get install -y ffmpeg; \
	fi
endif

env:
	@test -f .env || (cp .env.example .env && echo "created .env — add your keys")
	@test ! -f .env || echo ".env: OK"

# Run the bundled example through images -> voice -> assembly.
# Uses the free placeholder image backend, so it works with NO keys at all;
# with DASHSCOPE_API_KEY set, drop --backend placeholder for real images.
example: sync
	@test -d output/the-sharing-berry || cp -r examples/the-sharing-berry output/
	$(PY) -m pipeline.images output/the-sharing-berry --backend placeholder
	$(PY) -m pipeline.voiceover output/the-sharing-berry
	$(PY) -m pipeline.assemble output/the-sharing-berry
	@echo ""
	@echo "done — open output/the-sharing-berry/final.mp4"

clean-example:
	rm -rf output/the-sharing-berry
