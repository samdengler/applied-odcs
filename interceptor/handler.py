"""One interceptor Lambda for every governed target, deciding from the
policy files the registry publishes (policy_file.py).

The Gateway names each tool <target>___<tool>.  On a tools/call the
handler takes the target from the name, gets that target's policy
file, and hands the event to cedar-odcs's handlers built from it.  The
code holds nothing of any use case, so every Gateway runs the same
function, and a published policy file takes effect without a deploy.

  CEDAR_ODCS_POLICIES      s3://bucket/prefix/ in the Lambda, or a
                           directory for local runs; target hr's
                           file is <prefix>hr.json
  CEDAR_ODCS_POLICIES_TTL  seconds a loaded file is used before the
                           source is asked again (default 60)
  CEDAR_ODCS_CLAIMS        the token claims naming the subject, the
                           roles, and the actor, as JSON, e.g.
                           {"subject": "username", "roles": "cognito:groups"};
                           the default reads sub, roles, and act

A target's handlers are cached.  Once they are older than the TTL, the
next call asks the source again with the cached ETag and rebuilds them
only when the file changed.

Failing closed:
  - a target with no policy file is not governed: its tools are
    rejected as cedar-odcs rejects a tool its table does not name;
  - a file that cannot be read or built on first use rejects the call;
  - a file that cannot be re-read once loaded keeps deciding with the
    copy in memory, and logs a warning; a deleted file stops deciding
    at the next check.
Any other method (initialize, tools/list) passes without a file.

The routing reaches into cedar_odcs.gateway.handlers for _reject and
_request_id, so the Gateway's formats stay in one place.  This module
belongs in cedar-odcs, beside gateway/handler.py, once the approach is
settled.
"""

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from cedar_odcs.engine.identities import ClaimsMapping
from cedar_odcs.gateway.handlers import Handlers, _reject, _request_id

from interceptor.policy_file import SEPARATOR, ungoverned, use_case

log = logging.getLogger("cedar-odcs")
# A Gateway target name, never a path: it becomes part of a key or a file name.
TARGET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$")


class Missing(Exception):
    """The source has no policy file for the target."""


class Unavailable(Exception):
    """A target's policy file could not be read or built, and no copy is in memory."""


class S3Source:
    """Policy files in S3: s3://bucket/prefix/<target>.json."""

    def __init__(self, location: str, client=None):
        bucket, _, prefix = location.removeprefix("s3://").partition("/")
        self.bucket = bucket
        self.prefix = prefix if not prefix or prefix.endswith("/") else prefix + "/"
        self.client = client or boto3.client("s3")

    def get(self, target: str, etag: str | None = None):
        """(text, etag), or None when the object still has etag."""
        args = {"Bucket": self.bucket, "Key": f"{self.prefix}{target}.json"}
        if etag:
            args["IfNoneMatch"] = etag
        try:
            out = self.client.get_object(**args)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code")
            if code in ("304", "NotModified"):
                return None
            if code in ("404", "NoSuchKey"):
                raise Missing(f"s3://{self.bucket}/{args['Key']}") from e
            raise
        return out["Body"].read().decode(), out["ETag"]


class DirectorySource:
    """Policy files in a directory, for local runs: <directory>/<target>.json."""

    def __init__(self, directory):
        self.directory = Path(directory)

    def get(self, target: str, etag: str | None = None):
        path = self.directory / f"{target}.json"
        if not path.is_file():
            raise Missing(str(path))
        data = path.read_bytes()
        tag = hashlib.sha256(data).hexdigest()
        return None if tag == etag else (data.decode(), tag)


def source(location: str):
    return S3Source(location) if location.startswith("s3://") else DirectorySource(location)


@dataclass
class _Entry:
    handlers: Handlers | None  # None: the source has no file for the target
    etag: str | None
    checked: float


class PolicyFiles:
    """Each target's cedar-odcs handlers, built from its policy file."""

    def __init__(self, source, ttl: float = 60, claims: ClaimsMapping = ClaimsMapping(), clock=time.monotonic):
        self.source, self.ttl, self.claims, self.clock = source, ttl, claims, clock
        self._entries: dict[str, _Entry] = {}

    def handlers(self, target: str) -> Handlers | None:
        """The target's handlers, or None when no policy file governs it."""
        entry = self._entries.get(target)
        if entry is not None and self.clock() - entry.checked < self.ttl:
            return entry.handlers
        try:
            fetched = self.source.get(target, entry.etag if entry else None)
            if fetched is None:
                entry = _Entry(entry.handlers, entry.etag, self.clock())
            else:
                text, etag = fetched
                entry = _Entry(Handlers(use_case(json.loads(text), target, self.claims)), etag, self.clock())
                log.info("loaded %s's policy file %s", target, etag)
        except Missing:
            entry = _Entry(None, None, self.clock())
        except Exception as e:
            if entry is None or entry.handlers is None:
                raise Unavailable(f"{target}: {e}") from e
            log.warning("kept %s's policy file %s: %s", target, entry.etag, e)
            entry = _Entry(entry.handlers, entry.etag, self.clock())
        self._entries[target] = entry
        return entry.handlers


def _target(event: dict) -> str | None:
    """The target a well-formed tools/call names; None for anything else."""
    try:
        body = event["mcp"]["gatewayRequest"]["body"]
        if isinstance(body, str):
            body = json.loads(body)
        if body.get("method") != "tools/call":
            return None
        name = body["params"]["name"]
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    if not isinstance(name, str):
        return None
    target, separator, _ = name.partition(SEPARATOR)
    return target if separator and TARGET.match(target) else None


class Interceptor:
    """The two interception points, routed by target.  Anything without
    a policy file goes to handlers built from no tools, which pass
    every other method and reject every tool."""

    def __init__(self, policy_files: PolicyFiles):
        self.policy_files = policy_files
        self.ungoverned = Handlers(ungoverned(policy_files.claims))

    def _handlers(self, event: dict):
        target = _target(event)
        return self.ungoverned if target is None else (self.policy_files.handlers(target) or self.ungoverned)

    def request(self, event: dict, context=None) -> dict:
        try:
            handlers = self._handlers(event)
        except Unavailable as e:
            log.warning("rejected: %s", e)
            return _reject(_request_id(event), "request could not be evaluated: the target's policies could not be loaded")
        return handlers.request_handler(event, context)

    def response(self, event: dict, context=None) -> dict:
        try:
            handlers = self._handlers(event)
        except Unavailable as e:
            log.warning("response withheld: %s", e)
            return _reject(_request_id(event), "response withheld; the target's policies could not be loaded")
        return handlers.response_handler(event, context)


logging.getLogger("cedar-odcs").setLevel(logging.DEBUG if os.environ.get("CEDAR_ODCS_RECORD") else logging.INFO)
_INTERCEPTOR = None


def _interceptor() -> Interceptor:
    global _INTERCEPTOR
    if _INTERCEPTOR is None:
        claims = ClaimsMapping(**json.loads(os.environ.get("CEDAR_ODCS_CLAIMS") or "{}"))
        ttl = float(os.environ.get("CEDAR_ODCS_POLICIES_TTL", "60"))
        _INTERCEPTOR = Interceptor(PolicyFiles(source(os.environ["CEDAR_ODCS_POLICIES"]), ttl, claims))
    return _INTERCEPTOR


def request(event, context):
    return _interceptor().request(event, context)


def response(event, context):
    return _interceptor().response(event, context)
