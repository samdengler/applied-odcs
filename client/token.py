"""Cognito access tokens for the demo users.

`access_token(user)` signs in with USER_PASSWORD_AUTH and returns the access
token, which is what the Gateway validates.  Settings come from the
environment: APPLIED_ODCS_PASSWORD, CLIENT_ID, AWS_REGION.
"""

import base64
import json
import os
import sys


def access_token(user: str) -> str:
    import boto3

    client = boto3.client("cognito-idp", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    resp = client.initiate_auth(
        AuthFlow="USER_PASSWORD_AUTH",
        ClientId=os.environ["CLIENT_ID"],
        AuthParameters={"USERNAME": user, "PASSWORD": os.environ["APPLIED_ODCS_PASSWORD"]},
    )
    return resp["AuthenticationResult"]["AccessToken"]


def claims(token: str) -> dict:
    """Decode the payload segment of a JWT without verifying it."""
    segment = token.split(".")[1]
    segment += "=" * (-len(segment) % 4)
    return json.loads(base64.urlsafe_b64decode(segment))


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: token.py <user>", file=sys.stderr)
        return 2
    token = access_token(argv[0])
    payload = claims(token)
    print(token)
    print(f"username:       {payload.get('username')}", file=sys.stderr)
    print(f"cognito:groups: {payload.get('cognito:groups') or 'none'}", file=sys.stderr)
    print(f"client_id:      {payload.get('client_id')}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
