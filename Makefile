# applied-odcs: every verification in docs/plan.md is a target.
#
#   make check                       the pipeline gate, no AWS
#   make deploy && make users        the stack, then Alice, Carol, Dave
#   make call USER=carol TOOL=list_orders ARGS='{}'
#
# VARIANT selects the stack.  Empty is AppliedOdcs, which this branch never
# deploys; VARIANT=runtime is AppliedOdcsRuntime, with its own env file.

SHELL := /bin/bash
TOOL ?= list_orders
ARGS ?= {}
CEDAR_ODCS_CHECKOUT ?= ../cedar-odcs
VARIANT ?=
# scripts/demo.sh runs make again with ENV_FILE set to this.
ENV := $(or $(ENV_FILE),.env.applied-odcs$(if $(VARIANT),-$(VARIANT)))
STACK := $(if $(filter runtime,$(VARIANT)),AppliedOdcsRuntime,AppliedOdcs)
OUTPUTS := build/outputs$(if $(VARIANT),-$(VARIANT)).json
CDK := npx cdk -c variant=$(VARIANT)

.PHONY: sync build check prove bundle server-build server-smoke synth baseline compare-baseline deploy deploy-guard users token call tools record compare-live latency demo

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

# build/server for the Runtime: the MCP server and the tool's one data
# file, so orders.json has one source.
server-build:
	rm -rf build/server && mkdir -p build/server
	cp orders/server/server.py orders/server/requirements.txt orders/server/Dockerfile orders/tool/data/orders.json build/server/

# The server from build/server on the Mac, initialize and tools/list over HTTP.
server-smoke: server-build
	uv run python scripts/server_smoke.py

synth: bundle server-build
	cd infra && $(CDK) synth --quiet
	uv run python scripts/check_synth.py infra/cdk.out/$(STACK).template.json

# The default variant must synthesize what the demo-lambda-target tag
# did.  make baseline synthesizes the tag's sources from git archive into
# build/baseline-AppliedOdcs.template.json, with this checkout's
# node_modules and interceptor bundle; run it with the same AWS
# credentials as compare-baseline, since CDK writes the account into the
# template only when it can resolve one.
baseline: bundle
	rm -rf build/baseline-tag && mkdir -p build/baseline-tag/build
	git archive demo-lambda-target | tar -x -C build/baseline-tag
	ln -s $(CURDIR)/infra/node_modules build/baseline-tag/infra/node_modules
	cp -R build/lambda build/baseline-tag/build/lambda
	cd build/baseline-tag/infra && npx cdk synth --quiet
	cp build/baseline-tag/infra/cdk.out/AppliedOdcs.template.json build/baseline-AppliedOdcs.template.json

compare-baseline:
	cd infra && npx cdk -c variant= synth --quiet AppliedOdcs
	uv run python scripts/compare_templates.py build/baseline-AppliedOdcs.template.json infra/cdk.out/AppliedOdcs.template.json

# check is the gate: a contract or policy change that breaks the corpus
# does not deploy.  The outputs go to $(ENV) for the clients.  On the
# runtime-mcp branch only VARIANT=runtime deploys.
deploy: deploy-guard check bundle server-build
	cd infra && npm ci --silent && $(CDK) deploy $(STACK) --require-approval never --outputs-file ../$(OUTPUTS)
	uv run python scripts/env.py $(OUTPUTS) $(ENV)

deploy-guard:
	@if [ "$(VARIANT)" != runtime ]; then \
	  echo "make deploy: this branch deploys only AppliedOdcsRuntime; run make deploy VARIANT=runtime" >&2; exit 1; fi

users:
	uv run --env-file $(ENV) python scripts/users.py

token:
	uv run --env-file $(ENV) python -P client/token.py $(USER)

call:
	@uv run --env-file $(ENV) python -P client/call.py $(USER) $(TOOL) '$(ARGS)'

tools:
	@uv run --env-file $(ENV) python -P client/tools.py $(USER)

# Recordings from the runtime variant go to orders/tests/events/runtime.
record:
	RECORD_DIR=orders/tests/events$(if $(VARIANT),/$(VARIANT)) uv run --env-file $(ENV) python -P client/record.py $(USER) $(TOOL) '$(ARGS)'

# Ten timed tools/call round trips after two warmups; ENV_FILE picks the
# other stack's env file to time it from here.
latency:
	@uv run --env-file $(ENV) python -P client/latency.py $(USER) $(TOOL) 10 2

# Each runtime recording against its Lambda function target recording.
compare-live:
	uv run python scripts/compare_live.py

# docs/demo.md end to end, against the deployed Gateway.
demo:
	ENV_FILE=$(ENV) scripts/demo.sh
