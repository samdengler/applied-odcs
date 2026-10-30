"""Asserts what make synth must produce: one Gateway with a REQUEST and a
RESPONSE interceptor, both passing request headers, one target named hr,
one Cognito user pool, and both interceptors running the shared handler
with no use case in their environment, reading policy files from the one
policy bucket."""

import json
import sys
from pathlib import Path

template = json.loads(Path(sys.argv[1] if len(sys.argv) > 1 else "infra/cdk.out/AppliedOdcsShared.template.json").read_text())
resources = template["Resources"]
of = lambda t: [r["Properties"] for r in resources.values() if r["Type"] == t]  # noqa: E731

(gateway,) = of("AWS::BedrockAgentCore::Gateway")
interceptors = gateway["InterceptorConfigurations"]
assert sorted(p for i in interceptors for p in i["InterceptionPoints"]) == ["REQUEST", "RESPONSE"], interceptors
assert all(i["InputConfiguration"]["PassRequestHeaders"] is True for i in interceptors), interceptors
assert [t["Name"] for t in of("AWS::BedrockAgentCore::GatewayTarget")] == ["hr"]
assert len(of("AWS::Cognito::UserPool")) == 1

(bucket,) = [name for name, r in resources.items() if r["Type"] == "AWS::S3::Bucket"]
functions = {p["Handler"]: p for p in of("AWS::Lambda::Function") if "Handler" in p}
for point in ("request", "response"):
    env = functions[f"interceptor.handler.{point}"]["Environment"]["Variables"]
    assert "CEDAR_ODCS_USE_CASE" not in env, env
    assert bucket in json.dumps(env["CEDAR_ODCS_POLICIES"]), env
    assert json.loads(env["CEDAR_ODCS_CLAIMS"]) == {"subject": "username", "roles": "cognito:groups"}, env
grants = [p for p in of("AWS::IAM::Policy") if bucket in json.dumps(p) and "s3:GetObject" in json.dumps(p)]
assert len(grants) == 2, "both interceptors read the policy bucket"
print("synth ok: one Gateway, REQUEST and RESPONSE interceptors with PassRequestHeaders, target hr, one user pool, "
      "both interceptors on interceptor.handler reading the policy bucket")
