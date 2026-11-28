# Hermes Synapse — demo stand. Backend tests: `cd backend && uv run pytest`.
.PHONY: demo demo-reset evidence evidence-rebuild evidence-repack

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

# Verify the committed pack. Does not rewrite it. Drift exits non-zero.
evidence: demo
	$(EVIDENCE_PY)

# Intentional rebuild from a fresh `make demo` export. Overwrites pack files
# except PMM README/SUMMARY/PDF and existing decision-log zips.
evidence-rebuild: demo
	$(EVIDENCE_PY) --force-rebuild

# Rebuild MANIFEST.json + hermes-evidence-sample.zip from files already in
# docs/demo/evidence/. Does not re-export logs or rewrite PMM README/SUMMARY/PDF.
evidence-repack:
	$(EVIDENCE_PY) --repack
