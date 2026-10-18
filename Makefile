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

# build/lambda for both interceptors; the smoke test runs the bundle's
# handler on one fixture with the Mac's cedarpy standing in for the
# Linux wheel.
bundle:
	lambda/bundle.sh
	uv run python lambda/smoke.py

synth: bundle
	cd infra && npx cdk synth --quiet
	uv run python scripts/check_synth.py

# check is the gate: a contract or policy change that breaks the corpus
# does not deploy.  The outputs go to .env.applied-odcs for the clients.
deploy: check bundle
	cd infra && npm ci --silent && npx cdk deploy --require-approval never --outputs-file ../build/outputs.json
	uv run python scripts/env.py build/outputs.json

users:
	uv run --env-file $(ENV) python scripts/users.py

token:
	uv run --env-file $(ENV) python -P client/token.py $(USER)

call:
	@uv run --env-file $(ENV) python -P client/call.py $(USER) $(TOOL) '$(ARGS)'

record:
	uv run --env-file $(ENV) python -P client/record.py $(USER) $(TOOL) '$(ARGS)'

# docs/demo.md end to end, against the deployed Gateway.
demo:
	scripts/demo.sh
