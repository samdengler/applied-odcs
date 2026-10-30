#!/bin/bash
# Use case 1, an employee changes their own address, against the deployed
# Gateway.  Each step prints its command, then its output.  The Gateway
# decides every call from the call and the token before the tool runs, and
# cuts each result as its tool's model, with the policy file the
# interceptor read from S3.
set -u
cd "$(dirname "$0")/.."
ENV=.env.applied-odcs-shared
ADDRESS='{"line1":"48 Pine St","city":"Portland","postalCode":"04102","country":"US"}'

step() { printf '\n== %s\n$ %s\n' "$1" "$2"; eval "$2"; }

step "1. The one permit that decides whose address a call changes" \
  "sed -n '/@id(\"employee-updates-own-address\")/,/^};/p' hr/policies.cedar"
step "2. The policy file the interceptors read, in S3: each tool and the model it returns" \
  "uv run --env-file $ENV python -c \"import json, os, boto3; d = json.load(boto3.client('s3').get_object(Bucket=os.environ['POLICY_BUCKET'], Key='hr.json')['Body']); print(os.environ['POLICY_BUCKET'] + '/hr.json:', {t: v['model'] for t, v in d['tools'].items()}, len(d['entities']), 'entities', d['policies'].count('@id('), 'policies')\""
step "3. Alice's token names her" \
  "make -s token USER=alice 2>&1 >/dev/null | head -2"
step "4. Alice views her profile: the Employee model, without the bank account" \
  "make -s call USER=alice TOOL=get_profile ARGS='{\"employeeId\":\"alice\"}'"
step "5. Alice moves: the HR API records the change and tells payroll; the AddressChange model comes back without the fraud score" \
  "make -s call USER=alice TOOL=update_address ARGS='{\"employeeId\":\"alice\",\"address\":$ADDRESS}'"
step "6. Alice names Bob: refused on the request, the tool never runs" \
  "make -s call USER=alice TOOL=update_address ARGS='{\"employeeId\":\"bob\",\"address\":$ADDRESS}'"
step "7. Alice sends a salary inside the address: refused, named at its contract path" \
  "make -s call USER=alice TOOL=update_address ARGS='{\"employeeId\":\"alice\",\"address\":{\"line1\":\"48 Pine St\",\"city\":\"Portland\",\"postalCode\":\"04102\",\"country\":\"US\",\"salary\":250000}}'"
step "8. Bob views Alice's profile: refused on the request, the tool never runs" \
  "make -s call USER=bob TOOL=get_profile ARGS='{\"employeeId\":\"alice\"}'"
