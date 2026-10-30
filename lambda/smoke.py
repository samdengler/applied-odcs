"""Runs the shared interceptor from build/lambda on two fixtures, on the Mac.

The bundle's cedarpy is a Linux wheel and cannot load here, so the
venv's cedarpy is imported first.  The interceptor and cedar_odcs come
from build/lambda, as they will in the Lambda, and the policies from
build/policies/hr.json, as they will from S3.
"""

import json
import os
import sys
from pathlib import Path

import cedarpy  # noqa: F401  the macOS binding, before build/lambda is on the path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "build/lambda"
assert list((BUNDLE / "cedarpy").glob("_internal.cpython-312-aarch64-linux-gnu.so")), "no Linux arm64 cedarpy in the bundle"
assert not (BUNDLE / "hr").exists() and not list(BUNDLE.glob("interceptor/test_*")), "the bundle carries a use case or tests"
sys.path.insert(0, str(BUNDLE))
os.environ["CEDAR_ODCS_POLICIES"] = str(ROOT / "build/policies")

from interceptor import handler  # noqa: E402

assert Path(handler.__file__).is_relative_to(BUNDLE), handler.__file__
events = ROOT / "hr/tests/events"
own = handler.request(json.loads((events / "request-alice-updates-own-address.json").read_text()), None)
assert "transformedGatewayRequest" in own["mcp"], own
bobs = handler.request(json.loads((events / "request-alice-updates-bobs-address.json").read_text()), None)
message = bobs["mcp"]["transformedGatewayResponse"]["body"]["error"]["message"]
assert message == "UpdateEmployee is not permitted for this caller", message
print("bundle ok: the interceptor from build/lambda, with build/policies/hr.json, passes Alice's own address "
      f"and refuses Bob's: {message}")
