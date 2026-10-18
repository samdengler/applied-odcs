"""Rewrite the bearer tokens in orders/tests/events/*.json (except live-*.json).

Each token's payload is replaced by the matching file in orders/tests/identities/,
so the fixtures carry the Cognito access token shape.  Run it after changing an
identity file or copying in a fixture with an older token shape.  It is
idempotent.
"""
import base64, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent / "orders" / "tests"
IDS = {p.stem: json.loads(p.read_text()) for p in (ROOT / "identities").glob("*.json")}
SIG = "signature-checked-by-the-gateway"


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def identity(claims: dict) -> str:
    key = "username" if "username" in claims else "sub"
    if "act" in claims:
        return "carol-for-alice"
    return claims[key]


def new_token(token: str) -> str:
    head, payload, _ = token.split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    return f"{head}.{b64(json.dumps(IDS[identity(claims)], indent=2).encode())}.{SIG}"


def tokens(node):
    if isinstance(node, dict):
        for k, v in node.items():
            if k.lower() == "authorization" and isinstance(v, str) and v.startswith("Bearer "):
                yield v[7:]
            else:
                yield from tokens(v)
    elif isinstance(node, list):
        for v in node:
            yield from tokens(v)


for path in sorted((ROOT / "events").glob("*.json")):
    if path.name.startswith("live-"):
        continue
    text = path.read_text()
    for old in set(tokens(json.loads(text))):
        text = text.replace(old, new_token(old))
    path.write_text(text)
