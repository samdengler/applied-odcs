"""Runs the bundle's response handler on one fixture, on the Mac.

The bundle's cedarpy is a Linux wheel and cannot load here, so the
venv's cedarpy is imported first; everything else (cedar_odcs, the
orders descriptor, the generated Cedar files, entities.json) comes from
build/lambda, as it will in the Lambda.
"""

import json
import os
import sys
from pathlib import Path

import cedarpy  # noqa: F401  the macOS binding, before build/lambda is on the path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "build/lambda"
assert list((BUNDLE / "cedarpy").glob("_internal.cpython-312-aarch64-linux-gnu.so")), "no Linux arm64 cedarpy in the bundle"
sys.path.insert(0, str(BUNDLE))
os.environ["CEDAR_ODCS_USE_CASE"] = str(BUNDLE / "orders")

from cedar_odcs.gateway import handler  # noqa: E402

assert Path(handler.__file__).is_relative_to(BUNDLE), handler.__file__
event = json.loads((ROOT / "orders/tests/events/response-alice-reads-own-order.json").read_text())
out = handler.response(event, None)["mcp"]["transformedGatewayResponse"]
fields = sorted(out["body"]["result"]["structuredContent"])
assert "internalNotes" not in fields and "fraudScore" not in fields, fields
print("bundle ok: response handler from build/lambda returned", fields)
