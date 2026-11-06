# applied-odcs: every verification is a target.
#
#   make check                       the pipeline gate, with the directory's proofs; no AWS
#   make prove                       the directory's proofs alone
#   make deploy && make users        the stack, then Alice and Bob
#   make call USER=alice TOOL=update_address ARGS='{"employeeId":"alice","address":{...}}'
#   make call USER=bob TOOL=directory___look_up_employee ARGS='{"employeeId":"alice"}'
#   make publish                     both policy files to S3, no redeploy
#   make demo                        hr against the deployed Gateway
#   make demo-directory              the directory against the deployed Gateway

SHELL := /bin/bash
TOOL ?= get_profile
ARGS ?= {}
CEDAR_ODCS_CHECKOUT ?= ../cedar-odcs
ENV := .env.applied-odcs-shared

.PHONY: sync build check prove policies bundle synth deploy publish users token call record demo demo-directory

sync:
	uv sync
	cd infra && npm ci

build:
	uv run cedar-odcs build hr
	uv run cedar-odcs build directory

# The contract here is the source, so pull is not run.  There are no
# guardrails to prove.  cedar-odcs's tools gate wants every tool to return
# the whole Employee record; here each tool returns its own model, so the
# binding check in publish.py (interceptor/policy_file.py) replaces it.
# The directory has one model and guardrails, so cedar-odcs's own check
# runs whole on it: build, the tools gate, validate, the corpus, and the
# proofs, which need cargo and cvc5 (see ../cedar-odcs/analysis/README.md).
# A policy file without the restricted forbid fails here and is not published.
check:
	uv run cedar-odcs build hr
	uv run cedar-odcs validate hr
	uv run cedar-odcs run-tests hr
	uv run python scripts/publish.py hr
	CEDAR_ODCS_ANALYSIS=$(CEDAR_ODCS_CHECKOUT)/analysis uv run cedar-odcs check directory
	uv run python scripts/publish.py directory
	uv run pytest -q

prove:
	uv run cedar-odcs build directory
	CEDAR_ODCS_ANALYSIS=$(CEDAR_ODCS_CHECKOUT)/analysis uv run cedar-odcs prove directory

# build/policies/<target>.json: what the registry publishes for each target.
policies: build
	uv run python scripts/publish.py hr
	uv run python scripts/publish.py directory

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
# clients, and the policy files go to the bucket the stack made.
deploy: check bundle
	cd infra && npm ci --silent && npx cdk deploy AppliedOdcsShared --require-approval never --outputs-file ../build/outputs.json
	uv run python scripts/env.py build/outputs.json
	uv run --env-file $(ENV) python scripts/publish.py hr --upload
	uv run --env-file $(ENV) python scripts/publish.py directory --upload

# The registry's step, stood in for: check is the gate, then the policy
# files go to S3.  The interceptors use them within CEDAR_ODCS_POLICIES_TTL
# seconds; nothing is redeployed.
publish: check
	uv run --env-file $(ENV) python scripts/publish.py hr --upload
	uv run --env-file $(ENV) python scripts/publish.py directory --upload

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

# The directory against the deployed Gateway: a field labelled restricted
# never leaves, a published label changes the response with no deploy, and
# the proofs fail when the rule is weakened.  About three minutes: the relabel
# waits out the 60-second TTL twice.
demo-directory:
	scripts/demo-directory.sh
