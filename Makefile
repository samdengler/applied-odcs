# applied-odcs: every verification in docs/plan.md is a target.
#
#   make check                       the pipeline gate, no AWS
#   make deploy && make users        the stack, then Alice, Carol, Dave
#   make call USER=carol TOOL=list_orders ARGS='{}'

SHELL := /bin/bash
TOOL ?= list_orders
ARGS ?= {}
CEDAR_ODCS_CHECKOUT ?= ../cedar-odcs
ENV := .env.applied-odcs

.PHONY: sync build check prove bundle synth deploy users token call record demo

sync:
	uv sync
	cd infra && npm ci

build:
	uv run cedar-odcs build orders

# The contract here is the source, so pull is not run; prove needs cargo
# and cvc5 and is its own target.
check:
	uv run cedar-odcs check orders --skip pull --skip prove
	uv run pytest -q

prove: build
	CEDAR_ODCS_ANALYSIS=$(CEDAR_ODCS_CHECKOUT)/analysis uv run cedar-odcs prove orders

bundle synth deploy users token call record demo:
	@echo "make $@: not built yet (see docs/plan.md, Work order)"; exit 1
