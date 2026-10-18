"""Asserts what make synth must produce: one Gateway with a REQUEST and a
RESPONSE interceptor, both passing request headers, one target named
orders, and one Cognito user pool."""

import json
import sys
from pathlib import Path

template = json.loads(Path(sys.argv[1] if len(sys.argv) > 1 else "infra/cdk.out/AppliedOdcs.template.json").read_text())
of = lambda t: [r["Properties"] for r in template["Resources"].values() if r["Type"] == t]  # noqa: E731

(gateway,) = of("AWS::BedrockAgentCore::Gateway")
interceptors = gateway["InterceptorConfigurations"]
assert sorted(p for i in interceptors for p in i["InterceptionPoints"]) == ["REQUEST", "RESPONSE"], interceptors
assert all(i["InputConfiguration"]["PassRequestHeaders"] is True for i in interceptors), interceptors
assert [t["Name"] for t in of("AWS::BedrockAgentCore::GatewayTarget")] == ["orders"]
assert len(of("AWS::Cognito::UserPool")) == 1
print("synth ok: one Gateway, REQUEST and RESPONSE interceptors with PassRequestHeaders, target orders, one user pool")
