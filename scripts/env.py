"""Writes .env.applied-odcs from the stack outputs that cdk deploy saved.

The file is ignored by git.  It keeps APPLIED_ODCS_PASSWORD across
deploys and generates one the first time, meeting the Cognito default
policy (upper, lower, digit, symbol).  The password is never printed.
"""

import json
import secrets
import string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env.applied-odcs"
OUTPUTS = {"GatewayUrl": "GATEWAY_URL", "GatewayId": "GATEWAY_ID", "UserPoolId": "USER_POOL_ID",
           "ClientId": "CLIENT_ID", "Region": "AWS_REGION", "RequestLogGroup": "REQUEST_LOG_GROUP",
           "ResponseLogGroup": "RESPONSE_LOG_GROUP", "ToolLogGroup": "TOOL_LOG_GROUP"}


def _password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "Aa1-" + "".join(secrets.choice(alphabet) for _ in range(20))


def main(outputs_file: str) -> None:
    current = {}
    if ENV.exists():
        for line in ENV.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                current[key] = value
    if not current.get("APPLIED_ODCS_PASSWORD"):
        current["APPLIED_ODCS_PASSWORD"] = _password()
    stack = json.loads(Path(outputs_file).read_text())["AppliedOdcs"]
    for output, key in OUTPUTS.items():
        current[key] = stack[output]
    ENV.write_text("".join(f"{k}={v}\n" for k, v in current.items()))
    ENV.chmod(0o600)
    print(f"wrote {ENV.name}: " + ", ".join(k for k in current))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "build/outputs.json"))
