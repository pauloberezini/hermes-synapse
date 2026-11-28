# Hermes Synapse — demo stand. Backend tests: `cd backend && uv run pytest`.
.PHONY: demo demo-reset evidence

ROOT := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
export PYTHONPATH := $(ROOT)

VENV_PY := $(ROOT)backend/.venv/bin/python
ifeq ($(wildcard $(VENV_PY)),)
  DEMO_PY := python3 $(ROOT)scripts/demo.py
  EVIDENCE_PY := python3 $(ROOT)scripts/demo_evidence.py
else
  DEMO_PY := $(VENV_PY) $(ROOT)scripts/demo.py
  EVIDENCE_PY := $(VENV_PY) $(ROOT)scripts/demo_evidence.py
endif

PAUSE_FLAG :=
ifneq ($(PAUSE),)
  PAUSE_FLAG := --pause
endif

demo:
	$(DEMO_PY) $(PAUSE_FLAG)

demo-reset:
	$(DEMO_PY) --reset

evidence: demo
	$(EVIDENCE_PY)
