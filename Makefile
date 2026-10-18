# applied-odcs: every verification in docs/plan.md is a target.
# Step 2 stubs; each target is filled in by the step that builds it.

.PHONY: sync build check prove bundle synth deploy users token call record demo

sync:
	uv sync

build check prove bundle synth deploy users token call record demo:
	@echo "make $@: not built yet (see docs/plan.md, Work order)"; exit 1
