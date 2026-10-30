"""The shared interceptor decides from a policy file exactly as cedar-odcs's
handlers decide from the use case folder, routes each call to its
target's file, and fails closed when a file is missing or unreadable."""

import copy
import hashlib
import io
import json
import re
import shutil
from pathlib import Path

import boto3
import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber
from cedar_odcs.engine.identities import ClaimsMapping
from cedar_odcs.gateway.handlers import Handlers

from hr.usecase import USE_CASE
from interceptor.handler import (DirectorySource, Interceptor, Missing, PolicyFiles, S3Source, Unavailable,
                                 _target)
from interceptor.policy_file import from_folder, use_case

ROOT = Path(__file__).resolve().parents[1]
EVENTS = ROOT / "hr" / "tests" / "events"
LIVE = ROOT / "hr" / "tests" / "live"
COGNITO = ClaimsMapping(subject="username", roles="cognito:groups")
HR = from_folder(ROOT / "hr")


class Memory:
    """A source over a dict of target to policy file, recording each get."""

    def __init__(self, files: dict):
        self.files = files
        self.gets = []

    def get(self, target, etag=None):
        self.gets.append((target, etag))
        if target not in self.files:
            raise Missing(target)
        value = self.files[target]
        if isinstance(value, Exception):
            raise value
        text = json.dumps(value)
        tag = hashlib.sha256(text.encode()).hexdigest()
        return None if tag == etag else (text, tag)


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def interceptor(files=None, claims=ClaimsMapping(), ttl=60, clock=None):
    files = Memory({"hr": HR} if files is None else files)
    return Interceptor(PolicyFiles(files, ttl, claims, clock or Clock())), files


def event(name: str) -> dict:
    return json.loads((EVENTS / f"{name}.json").read_text())


def tool_call(name: str, arguments: dict, claims: dict) -> dict:
    """A request event for a tool call, with an unsigned token for claims."""
    import base64

    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    body = {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    return {"interceptorInputVersion": "1.0",
            "mcp": {"gatewayRequest": {"headers": {"Authorization": f"Bearer e30.{payload}.sig"}, "body": body}}}


def error(out: dict) -> str | None:
    response = out["mcp"].get("transformedGatewayResponse")
    return response and response["body"]["error"]["message"]


ALICE = {"sub": "alice", "roles": ["employee"]}
ADDRESS = {"homeAddress": {"line1": "48 Pine St"}}


# ---- the policy file


def test_the_policy_file_carries_the_contract_and_roles_and_no_users_or_records():
    assert {e["uid"]["type"] for e in HR["entities"]} == {"Contract", "Role"}
    assert {e["uid"]["id"] for e in HR["entities"] if e["uid"]["type"] == "Contract"} == {"Employee", "Employee/writers"}
    assert HR["target"] == "hr"
    assert HR["tools"] == USE_CASE.tools
    assert HR["policies"] == USE_CASE.policies
    assert set(HR) == {"format", "target", "resource", "tools", "entities", "policies"}


def test_the_policy_file_reads_back_as_the_descriptor():
    loaded = use_case(json.loads(json.dumps(HR)), "hr")
    for key in ("resource_type", "id_field", "attributes", "read_action", "read_field_action", "field_actions", "tools"):
        assert getattr(loaded, key) == getattr(USE_CASE, key), key


def test_a_descriptor_whose_verbs_break_the_convention_is_not_published(tmp_path):
    folder = shutil.copytree(ROOT / "hr", tmp_path / "hr", ignore=shutil.ignore_patterns("__pycache__"))
    descriptor = folder / "usecase.py"
    descriptor.write_text(descriptor.read_text().replace("""read_action='Action::"ReadEmployee"'""",
                                                         """read_action='Action::"SeeEmployee"'"""))
    with pytest.raises(ValueError, match="derives"):
        from_folder(folder)


@pytest.mark.parametrize("change,message", [
    ({"format": 2}, "format"),
    ({"target": "orders"}, "not 'hr'"),
    ({"policies": "permit(principal, action, resource) whe { true };"}, "condition"),
])
def test_a_bad_policy_file_is_refused_when_it_loads(change, message):
    with pytest.raises(ValueError, match=message):
        use_case({**HR, **change}, "hr")


# ---- the same decisions as the folder


def _fixtures():
    for path in sorted(EVENTS.glob("*.json")):
        yield pytest.param("request" if path.name.startswith("request-") else "response", path.stem, id=path.stem)


@pytest.mark.parametrize("point,name", list(_fixtures()))
def test_every_fixture_is_decided_as_the_folder_decides_it(point, name):
    shared, _ = interceptor()
    folder = Handlers(USE_CASE)
    expected = getattr(folder, f"{point}_handler")(event(name))
    assert getattr(shared, point)(copy.deepcopy(event(name))) == expected


@pytest.mark.parametrize("path", sorted(LIVE.glob("live-*.json")), ids=lambda p: p.stem)
def test_live_recording_matches_the_shared_interceptor(path):
    """A call recorded through the deployed Gateway, replayed through the
    interceptor with Cognito's claims, decides what the Gateway returned."""
    fixture = json.loads(path.read_text())
    observed = fixture["observed"]
    shared, _ = interceptor(claims=COGNITO)
    out = shared.request(fixture["request"])["mcp"]
    if observed["status"] == 403 or "error" in (observed["body"] or {}):
        assert out["transformedGatewayResponse"]["body"]["error"]["message"] == observed["body"]["error"]["message"]
        return
    assert "transformedGatewayRequest" in out
    if fixture["response"] is not None:
        body = shared.response(fixture["response"])["mcp"]["transformedGatewayResponse"]["body"]
        assert json.loads(body["result"]["content"][0]["text"]) == json.loads(observed["body"]["result"]["content"][0]["text"])


# ---- use case 1: an employee changes their own address


def test_alice_changes_her_own_address():
    shared, _ = interceptor()
    out = shared.request(tool_call("hr___update_employee", {"employeeId": "alice", "changes": ADDRESS}, ALICE))
    assert "transformedGatewayRequest" in out["mcp"]


def test_alice_may_not_change_bobs_address():
    shared, _ = interceptor()
    out = shared.request(tool_call("hr___update_employee", {"employeeId": "bob", "changes": ADDRESS}, ALICE))
    assert error(out) == "UpdateEmployee is not permitted for this caller"


def test_alice_may_not_change_her_own_salary():
    shared, _ = interceptor()
    changes = {**ADDRESS, "salary": 250000}
    out = shared.request(tool_call("hr___update_employee", {"employeeId": "alice", "changes": changes}, ALICE))
    assert error(out) == "UpdateEmployee rejected; fields not permitted: salary"


def test_cognito_claims_name_the_caller():
    shared, _ = interceptor(claims=COGNITO)
    claims = {"sub": "5f1c-uuid", "username": "alice", "cognito:groups": ["employee"]}
    own = shared.request(tool_call("hr___update_employee", {"employeeId": "alice", "changes": ADDRESS}, claims))
    other = shared.request(tool_call("hr___update_employee", {"employeeId": "bob", "changes": ADDRESS}, claims))
    assert "transformedGatewayRequest" in own["mcp"]
    assert error(other) == "UpdateEmployee is not permitted for this caller"


# ---- routing


def test_each_target_is_decided_by_its_own_file():
    """A second target whose file grants no self-service write: the same
    call shape is allowed on hr and refused on people."""
    people = json.loads(json.dumps(HR).replace("hr___", "people___"))
    people["target"] = "people"
    people["policies"] = re.sub(r'@id\("employee-updates-own-record"\).*?\};', "", HR["policies"], flags=re.S)
    shared, files = interceptor({"hr": HR, "people": people})
    arguments = {"employeeId": "alice", "changes": ADDRESS}
    assert "transformedGatewayRequest" in shared.request(tool_call("hr___update_employee", arguments, ALICE))["mcp"]
    refused = shared.request(tool_call("people___update_employee", arguments, ALICE))
    assert error(refused) == "UpdateEmployee is not permitted for this caller"
    assert [target for target, _ in files.gets] == ["hr", "people"]


def test_other_methods_pass_without_a_policy_file():
    shared, files = interceptor()
    out = shared.request(event("request-alice-updates-own-address") | {"mcp": {"gatewayRequest": {
        "headers": {}, "body": {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}}}})
    assert out["mcp"]["transformedGatewayRequest"]["body"]["method"] == "tools/list"
    assert files.gets == []


def test_a_target_with_no_policy_file_is_not_governed():
    shared, _ = interceptor()
    out = shared.request(tool_call("payroll___update_salary", {"employeeId": "alice"}, ALICE))
    assert error(out) == "tool payroll___update_salary is not governed; no policy covers it"


def test_the_response_of_an_ungoverned_tool_is_withheld():
    shared, _ = interceptor()
    response = event("response-alice-reads-own-record")
    response["mcp"]["gatewayRequest"]["body"]["params"]["name"] = "payroll___get_employee"
    out = shared.response(response)
    assert out["mcp"]["transformedGatewayResponse"]["statusCode"] == 403


@pytest.mark.parametrize("name", ["../etc___x", "hr", "___x", "a/b___x", 7])
def test_a_tool_name_that_names_no_target_never_reaches_the_source(name):
    shared, files = interceptor()
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": {}}}
    assert _target({"mcp": {"gatewayRequest": {"body": body}}}) is None
    shared.request({"mcp": {"gatewayRequest": {"headers": {}, "body": body}}})
    assert files.gets == []


# ---- loading, caching, and failing closed


def test_a_file_that_cannot_be_read_on_first_use_rejects_the_call():
    shared, _ = interceptor({"hr": RuntimeError("throttled")})
    out = shared.request(tool_call("hr___update_employee", {"employeeId": "alice", "changes": ADDRESS}, ALICE))
    assert error(out) == "request could not be evaluated: the target's policies could not be loaded"
    response = shared.response(event("response-alice-reads-own-record"))
    assert response["mcp"]["transformedGatewayResponse"]["body"]["error"]["message"] == (
        "response withheld; the target's policies could not be loaded")


def test_a_published_change_takes_effect_after_the_ttl():
    clock = Clock()
    shared, files = interceptor(clock=clock, ttl=60)
    call = tool_call("hr___update_employee", {"employeeId": "alice", "changes": ADDRESS}, ALICE)
    assert "transformedGatewayRequest" in shared.request(call)["mcp"]
    files.files["hr"] = {**HR, "policies": re.sub(r'@id\("employee-updates-own-record"\).*?\};', "",
                                                   HR["policies"], flags=re.S)}
    clock.now = 59
    assert "transformedGatewayRequest" in shared.request(call)["mcp"]
    assert len(files.gets) == 1
    clock.now = 60
    assert error(shared.request(call)) == "UpdateEmployee is not permitted for this caller"
    assert files.gets[1][1] is not None  # asked with the cached ETag


def test_an_unchanged_file_keeps_its_handlers():
    clock = Clock()
    policy_files = PolicyFiles(Memory({"hr": HR}), 60, ClaimsMapping(), clock)
    first = policy_files.handlers("hr")
    clock.now = 120
    assert policy_files.handlers("hr") is first


def test_a_file_that_cannot_be_reread_keeps_the_copy_in_memory():
    clock = Clock()
    shared, files = interceptor(clock=clock)
    call = tool_call("hr___update_employee", {"employeeId": "alice", "changes": ADDRESS}, ALICE)
    shared.request(call)
    files.files["hr"] = RuntimeError("throttled")
    clock.now = 600
    assert "transformedGatewayRequest" in shared.request(call)["mcp"]


def test_a_deleted_file_stops_governing_at_the_next_check():
    clock = Clock()
    shared, files = interceptor(clock=clock)
    call = tool_call("hr___update_employee", {"employeeId": "alice", "changes": ADDRESS}, ALICE)
    shared.request(call)
    del files.files["hr"]
    clock.now = 600
    assert error(shared.request(call)) == "tool hr___update_employee is not governed; no policy covers it"


def test_a_directory_source_reads_target_files(tmp_path):
    (tmp_path / "hr.json").write_text(json.dumps(HR))
    directory = DirectorySource(tmp_path)
    text, tag = directory.get("hr")
    assert json.loads(text) == HR
    assert directory.get("hr", tag) is None
    with pytest.raises(Missing):
        directory.get("payroll")


# ---- S3


def _s3():
    client = boto3.client("s3", region_name="us-east-1", aws_access_key_id="x", aws_secret_access_key="x")
    return client, Stubber(client)


def test_s3_source_reads_the_target_key_and_its_etag():
    client, stub = _s3()
    data = json.dumps(HR).encode()
    stub.add_response("get_object", {"Body": StreamingBody(io.BytesIO(data), len(data)), "ETag": '"abc"'},
                      {"Bucket": "policies", "Key": "gateways/hr.json"})
    with stub:
        assert S3Source("s3://policies/gateways", client).get("hr") == (data.decode(), '"abc"')


def test_s3_source_asks_with_the_etag_and_takes_304_as_unchanged():
    client, stub = _s3()
    stub.add_client_error("get_object", service_error_code="304", http_status_code=304,
                          expected_params={"Bucket": "policies", "Key": "hr.json", "IfNoneMatch": '"abc"'})
    with stub:
        assert S3Source("s3://policies/", client).get("hr", '"abc"') is None


def test_s3_source_takes_no_such_key_as_missing_and_raises_the_rest():
    client, stub = _s3()
    stub.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)
    stub.add_client_error("get_object", service_error_code="AccessDenied", http_status_code=403)
    with stub:
        source = S3Source("s3://policies", client)
        with pytest.raises(Missing):
            source.get("hr")
        with pytest.raises(Exception, match="AccessDenied"):
            source.get("hr")
