#!/bin/bash
# Use case 1, an employee changes their own address, against the deployed
# Gateway.  Each step prints its command, then its output.  The Gateway
# decides every call from the call and the token before the tool runs, and
# cuts the record the tool returns, with the policy file the interceptor
# read from S3.
set -u
cd "$(dirname "$0")/.."
ENV=.env.applied-odcs-shared
ADDRESS='{"homeAddress":{"line1":"48 Pine St","city":"Portland","postalCode":"04102","country":"US"}}'

step() { printf '\n== %s\n$ %s\n' "$1" "$2"; eval "$2"; }

step "1. The one permit that decides whose record a write changes" \
  "sed -n '/@id(\"employee-updates-own-record\")/,/^};/p' hr/policies.cedar"
step "2. The policy file the interceptors read, in S3" \
  "uv run --env-file $ENV python -c \"import json, os, boto3; d = json.load(boto3.client('s3').get_object(Bucket=os.environ['POLICY_BUCKET'], Key='hr.json')['Body']); print(os.environ['POLICY_BUCKET'] + '/hr.json:', sorted(d['tools']), len(d['entities']), 'entities', d['policies'].count('@id('), 'policies')\""
step "3. Alice's token names her" \
  "make -s token USER=alice 2>&1 >/dev/null | head -2"
step "4. Alice changes her own address: the Gateway forwards it, the tool writes it, and the record comes back without the bank account" \
  "make -s call USER=alice TOOL=update_employee ARGS='{\"employeeId\":\"alice\",\"changes\":$ADDRESS}'"
step "5. Alice names Bob: refused on the request, the tool never runs" \
  "make -s call USER=alice TOOL=update_employee ARGS='{\"employeeId\":\"bob\",\"changes\":$ADDRESS}'"
step "6. Alice changes her address and her salary: refused whole, naming the salary" \
  "make -s call USER=alice TOOL=update_employee ARGS='{\"employeeId\":\"alice\",\"changes\":{\"homeAddress\":{\"line1\":\"48 Pine St\"},\"salary\":250000}}'"
step "7. Bob reads Alice's record: refused on the request, the tool never runs" \
  "make -s call USER=bob TOOL=get_employee ARGS='{\"employeeId\":\"alice\"}'"
