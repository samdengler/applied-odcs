# applied-odcs: every verification is a target.
#
#   make check                       the pipeline gate, no AWS
#   make deploy && make users        the stack, then Alice and Bob
#   make call USER=alice TOOL=update_address ARGS='{"employeeId":"alice","address":{...}}'
#   make publish                     the policy file to S3, no redeploy

SHELL := /bin/bash
TOOL ?= get_profile
ARGS ?= {}
ENV := .env.applied-odcs-shared

.PHONY: sync build check policies bundle synth deploy publish users token call record demo

sync:
	uv sync
	cd infra && npm ci

build:
	uv run cedar-odcs build hr

# The contract here is the source, so pull is not run.  There are no
# guardrails to prove.  cedar-odcs's tools gate wants every tool to return
# the whole Employee record; here each tool returns its own model, so the
# binding check in publish.py (interceptor/policy_file.py) replaces it.
check:
	uv run cedar-odcs build hr
	uv run cedar-odcs validate hr
	uv run cedar-odcs run-tests hr
	uv run python scripts/publish.py hr
	uv run pytest -q

# build/policies/hr.json: what the registry publishes for target hr.
policies: build
	uv run python scripts/publish.py hr

# build/lambda for both interceptors, with no use case in it; the smoke
# test runs the bundle's handler on the policy file with the Mac's
# cedarpy standing in for the Linux wheel.
bundle: policies
	lambda/bundle.sh
	uv run python lambda/smoke.py

synth: bundle
	cd infra && npx cdk synth --quiet
	uv run python scripts/check_synth.py

# check is the gate: a contract or policy change that breaks the corpus
# does not deploy.  The outputs go to .env.applied-odcs-shared for the
# clients, and the policy file goes to the bucket the stack made.
deploy: check bundle
	cd infra && npm ci --silent && npx cdk deploy AppliedOdcsShared --require-approval never --outputs-file ../build/outputs.json
	uv run python scripts/env.py build/outputs.json
	uv run --env-file $(ENV) python scripts/publish.py hr --upload

# The registry's step, stood in for: check is the gate, then the policy
# file goes to S3.  The interceptors use it within CEDAR_ODCS_POLICIES_TTL
# seconds; nothing is redeployed.
publish: check
	uv run --env-file $(ENV) python scripts/publish.py hr --upload

users:
	uv run --env-file $(ENV) python scripts/users.py

token:
	uv run --env-file $(ENV) python -P client/token.py $(USER)

call:
	@uv run --env-file $(ENV) python -P client/call.py $(USER) $(TOOL) '$(ARGS)'

record:
	uv run --env-file $(ENV) python -P client/record.py $(USER) $(TOOL) '$(ARGS)'

# Use case 1, an employee changes their own address, against the deployed Gateway.
demo:
	scripts/demo.sh
