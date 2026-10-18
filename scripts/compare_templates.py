"""Compares two synthesized templates apart from asset hashes.

`compare_templates.py <baseline> <candidate>`: exits 0 when the templates
are identical once every asset hash (a 64 hex digit string, alone or inside
an S3 key or a metadata path) is replaced with a placeholder.  Otherwise
prints each differing path and exits 1.
"""

import json
import re
import sys
from pathlib import Path

ASSET_HASH = re.compile(r"[0-9a-f]{64}")


def normalize(value):
    if isinstance(value, str):
        return ASSET_HASH.sub("<asset-hash>", value)
    if isinstance(value, list):
        return [normalize(v) for v in value]
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items()}
    return value


def load(path: str) -> dict:
    return normalize(json.loads(Path(path).read_text()))


def differences(a, b, path="$"):
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            if key not in a:
                yield f"{path}.{key}: only in candidate"
            elif key not in b:
                yield f"{path}.{key}: only in baseline"
            else:
                yield from differences(a[key], b[key], f"{path}.{key}")
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            yield from differences(x, y, f"{path}[{i}]")
    elif a != b:
        yield f"{path}: {json.dumps(a)} != {json.dumps(b)}"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: compare_templates.py <baseline> <candidate>", file=sys.stderr)
        return 2
    found = list(differences(load(argv[0]), load(argv[1])))
    for line in found:
        print(line)
    if found:
        print(f"templates differ: {len(found)} difference(s)", file=sys.stderr)
        return 1
    print(f"templates identical apart from asset hashes: {argv[0]} and {argv[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
