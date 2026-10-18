"""Writes the env file from the stack outputs that cdk deploy saved.

`env.py <outputs file> <env file>`: the outputs file holds one stack, whose
key is AppliedOdcs or AppliedOdcsRuntime; the env file is .env.applied-odcs
or .env.applied-odcs-runtime, and is ignored by git.  It keeps
APPLIED_ODCS_PASSWORD across deploys and generates one the first time,
meeting the Cognito default policy (upper, lower, digit, symbol).  For the
runtime variant it also writes M2M_CLIENT_SECRET, read from Cognito.  Neither
secret is ever printed.
"""

import json
import secrets
import string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = {"GatewayUrl": "GATEWAY_URL", "GatewayId": "GATEWAY_ID", "UserPoolId": "USER_POOL_ID",
           "ClientId": "CLIENT_ID", "Region": "AWS_REGION", "RequestLogGroup": "REQUEST_LOG_GROUP",
           "ResponseLogGroup": "RESPONSE_LOG_GROUP", "ToolLogGroup": "TOOL_LOG_GROUP",
           "RuntimeArn": "RUNTIME_ARN", "RuntimeLogGroup": "RUNTIME_LOG_GROUP",
           "M2MClientId": "M2M_CLIENT_ID", "TokenEndpoint": "TOKEN_ENDPOINT"}


def _password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "Aa1-" + "".join(secrets.choice(alphabet) for _ in range(20))


def _client_secret(region: str, pool: str, client: str) -> str:
    import boto3

    idp = boto3.client("cognito-idp", region_name=region)
    return idp.describe_user_pool_client(UserPoolId=pool, ClientId=client)["UserPoolClient"]["ClientSecret"]


def main(outputs_file: str, env_file: str) -> None:
    env = Path(env_file)
    current = {}
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                current[key] = value
    if not current.get("APPLIED_ODCS_PASSWORD"):
        current["APPLIED_ODCS_PASSWORD"] = _password()
    (stack,) = json.loads(Path(outputs_file).read_text()).values()
    for output, key in OUTPUTS.items():
        if output in stack:
            current[key] = stack[output]
    if "M2MClientId" in stack:
        current["M2M_CLIENT_SECRET"] = _client_secret(stack["Region"], stack["UserPoolId"], stack["M2MClientId"])
    # Create the file private before the password goes in.
    env.touch(mode=0o600)
    env.chmod(0o600)
    env.write_text("".join(f"{k}={v}\n" for k, v in current.items()))
    print(f"wrote {env.name}: " + ", ".join(k for k in current))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "build/outputs.json"),
         sys.argv[2] if len(sys.argv) > 2 else str(ROOT / ".env.applied-odcs"))
