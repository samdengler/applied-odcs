"""Asserts what make synth must produce: one Gateway with a REQUEST and a
RESPONSE interceptor, both passing request headers, one target named
orders, and one Cognito user pool.

For AppliedOdcs the target is the tool Lambda.  For AppliedOdcsRuntime it
is an MCP server target calling an MCP Runtime with OAuth, and the
Runtime admits only the M2M client."""

import json
import sys
from pathlib import Path

path = Path(sys.argv[1] if len(sys.argv) > 1 else "infra/cdk.out/AppliedOdcs.template.json")
template = json.loads(path.read_text())
resources = template["Resources"]
of = lambda t: [r["Properties"] for r in resources.values() if r["Type"] == t]  # noqa: E731

(gateway,) = of("AWS::BedrockAgentCore::Gateway")
interceptors = gateway["InterceptorConfigurations"]
assert sorted(p for i in interceptors for p in i["InterceptionPoints"]) == ["REQUEST", "RESPONSE"], interceptors
assert all(i["InputConfiguration"]["PassRequestHeaders"] is True for i in interceptors), interceptors
(target,) = of("AWS::BedrockAgentCore::GatewayTarget")
assert target["Name"] == "orders", target["Name"]
assert len(of("AWS::Cognito::UserPool")) == 1

if path.name.startswith("AppliedOdcsRuntime."):
    assert "McpServer" in target["TargetConfiguration"]["Mcp"], target["TargetConfiguration"]
    endpoint = json.dumps(target["TargetConfiguration"]["Mcp"]["McpServer"]["Endpoint"])
    assert "/invocations?qualifier=DEFAULT" in endpoint and "%3A" in endpoint and "%2F" in endpoint, endpoint
    (credential,) = target["CredentialProviderConfigurations"]
    oauth = credential["CredentialProvider"]["OauthCredentialProvider"]
    assert credential["CredentialProviderType"] == "OAUTH" and oauth["GrantType"] == "CLIENT_CREDENTIALS", credential
    assert oauth["Scopes"] == ["orders/invoke"], oauth
    assert len(of("AWS::BedrockAgentCore::OAuth2CredentialProvider")) == 1
    (runtime,) = of("AWS::BedrockAgentCore::Runtime")
    assert runtime["ProtocolConfiguration"] == "MCP", runtime["ProtocolConfiguration"]
    jwt = runtime["AuthorizerConfiguration"]["CustomJWTAuthorizer"]
    m2m = [k for k, r in resources.items() if r["Type"] == "AWS::Cognito::UserPoolClient"
           and r["Properties"].get("AllowedOAuthFlows") == ["client_credentials"]]
    assert jwt["AllowedClients"] == [{"Ref": m2m[0]}], jwt
    assert not any(k.startswith("OrdersTool") for k in resources), "tool Lambda in the runtime variant"
    assert all(o in template["Outputs"] for o in ("RuntimeArn", "RuntimeLogGroup")), list(template["Outputs"])
    print("synth ok: one Gateway, REQUEST and RESPONSE interceptors with PassRequestHeaders, MCP server target orders "
          "with OAuth client credentials, an MCP Runtime admitting only the M2M client, one user pool")
else:
    assert "Lambda" in target["TargetConfiguration"]["Mcp"], target["TargetConfiguration"]
    print("synth ok: one Gateway, REQUEST and RESPONSE interceptors with PassRequestHeaders, target orders, one user pool")
