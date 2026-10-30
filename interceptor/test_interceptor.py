"""The shared interceptor decides from a policy file with cedar-odcs's
handlers, one per model, routes each call to its target's file and each
result to its tool's model, and fails closed when a file is missing or
unreadable."""

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
from interceptor.policy_file import from_folder, models

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


ALICE = {"sub": "alice"}
ADDRESS = {"line1": "48 Pine St", "city": "Portland", "postalCode": "04102", "country": "US"}


def update_address(employee: str, claims: dict = ALICE, address: dict = ADDRESS, target: str = "hr") -> dict:
    return tool_call(f"{target}___update_address", {"employeeId": employee, "address": address}, claims)


def without(policy_id: str, document: dict = HR) -> dict:
    return {**document, "policies": re.sub(rf'@id\("{policy_id}"\).*?\}};', "", document["policies"], flags=re.S)}


# ---- the policy file


def test_the_policy_file_carries_the_contract_and_no_users_or_records():
    assert HR["format"] == 2 and HR["target"] == "hr"
    assert {e["uid"]["id"] for e in HR["entities"]} == {
        "Employee", "Employee/writers", "AddressChange", "AddressChange/writers"}
    assert {e["uid"]["type"] for e in HR["entities"]} == {"Contract"}
    assert HR["tools"] == USE_CASE.tools
    assert HR["policies"] == USE_CASE.policies
    assert set(HR) == {"format", "target", "resource", "models", "tools", "entities", "policies"}


def test_the_policy_file_reads_back_as_one_use_case_per_leg_and_model():
    request, responses, tool_models, writes = models(json.loads(json.dumps(HR)), "hr")
    for key in ("resource_type", "id_field", "attributes", "read_action", "read_field_action", "field_actions", "tools"):
        assert getattr(request, key) == getattr(USE_CASE, key), key
    change = responses["AddressChange"]
    assert (change.resource_type, change.id_field, change.read_action, change.read_field_action) == (
        "AddressChange", "changeId", 'Action::"ReadAddressChange"', 'Action::"ReadAddressChangeField"')
    assert set(change.tools) == {"hr___update_address"} and set(responses["Employee"].tools) == {"hr___get_profile"}
    assert tool_models == {"hr___get_profile": "Employee", "hr___update_address": "AddressChange"}
    assert writes == {'Action::"UpdateAddress"': "homeAddress"}


def test_a_descriptor_whose_verbs_break_the_convention_is_not_published(tmp_path):
    folder = shutil.copytree(ROOT / "hr", tmp_path / "hr", ignore=shutil.ignore_patterns("__pycache__"))
    descriptor = folder / "usecase.py"
    descriptor.write_text(descriptor.read_text().replace("""read_action='Action::"ReadEmployee"'""",
                                                         """read_action='Action::"SeeEmployee"'"""))
    with pytest.raises(ValueError, match="derives"):
        from_folder(folder)


def _binding(tmp_path, edit):
    folder = shutil.copytree(ROOT / "hr", tmp_path / "hr", ignore=shutil.ignore_patterns("__pycache__"))
    schemas = json.loads((folder / "tools.json").read_text())
    edit(schemas)
    (folder / "tools.json").write_text(json.dumps(schemas))
    return folder


def test_a_tool_whose_output_is_not_its_model_is_not_published(tmp_path):
    def returns_salary(schemas):
        schemas[1]["outputSchema"]["properties"]["salary"] = {"type": "number"}
    with pytest.raises(ValueError, match=r"hr___update_address: outputSchema and model AddressChange differ: "
                                         r"only in outputSchema \['salary'\]"):
        from_folder(_binding(tmp_path, returns_salary))


def test_a_payload_that_is_not_the_field_it_writes_is_not_published(tmp_path):
    def sends_region(schemas):
        schemas[1]["inputSchema"]["properties"]["address"]["properties"]["region"] = {"type": "string"}
    with pytest.raises(ValueError, match=r"payload address and homeAddress differ: only in the payload "
                                         r"\['homeAddress.region'\]"):
        from_folder(_binding(tmp_path, sends_region))


@pytest.mark.parametrize("change,message", [
    ({"format": 3}, "format"),
    ({"target": "orders"}, "not 'hr'"),
    ({"policies": "permit(principal, action, resource) whe { true };"}, "condition"),
    ({"resource": "Payslip"}, "does not define"),
])
def test_a_bad_policy_file_is_refused_when_it_loads(change, message):
    with pytest.raises(ValueError, match=message):
        models({**HR, **change}, "hr")


def test_a_format_1_file_reads_back_as_one_model_for_every_tool():
    document = {"format": 1, "target": "hr",
                "resource": {"type": "Employee", "id": "employeeId", "attributes": {"employeeId": "User"}},
                "tools": {"hr___get_profile": {k: v for k, v in HR["tools"]["hr___get_profile"].items() if k != "model"}},
                "entities": HR["entities"], "policies": HR["policies"]}
    shared, _ = interceptor({"hr": document})
    seen = shared.response(event("response-alice-views-own-profile"))
    assert "bankAccount" not in json.loads(seen["mcp"]["transformedGatewayResponse"]["body"]["result"]["content"][0]["text"])


# ---- one model, the same decisions as cedar-odcs's own handlers


def _profile_fixtures():
    for path in sorted(EVENTS.glob("*.json")):
        if "get_profile" in path.read_text():
            yield pytest.param("request" if path.name.startswith("request-") else "response", path.stem, id=path.stem)


@pytest.mark.parametrize("point,name", list(_profile_fixtures()))
def test_a_one_model_tool_is_decided_as_cedar_odcs_decides_it(point, name):
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
    assert "transformedGatewayRequest" in shared.request(update_address("alice"))["mcp"]


def test_alice_may_not_change_bobs_address():
    shared, _ = interceptor()
    assert error(shared.request(update_address("bob"))) == "UpdateAddress is not permitted for this caller"


def test_a_salary_sent_inside_the_address_is_refused_at_its_contract_path():
    shared, _ = interceptor()
    out = shared.request(update_address("alice", address={**ADDRESS, "salary": 250000}))
    assert error(out) == "UpdateAddress rejected; fields not permitted: homeAddress.salary"


def test_each_result_is_filtered_as_its_tools_model():
    shared, _ = interceptor()
    profile = shared.response(event("response-alice-views-own-profile"))
    change = shared.response(event("response-alice-updates-own-address"))
    text = lambda out: json.loads(out["mcp"]["transformedGatewayResponse"]["body"]["result"]["content"][0]["text"])  # noqa: E731
    assert "bankAccount" not in text(profile) and "salary" in text(profile)
    assert "fraudScore" not in text(change) and text(change)["changeId"] == "chg-0001"


def test_cognito_claims_name_the_caller():
    shared, _ = interceptor(claims=COGNITO)
    claims = {"sub": "5f1c-uuid", "username": "alice"}
    assert "transformedGatewayRequest" in shared.request(update_address("alice", claims))["mcp"]
    assert error(shared.request(update_address("bob", claims))) == "UpdateAddress is not permitted for this caller"


# ---- routing


def test_each_target_is_decided_by_its_own_file():
    """A second target whose file grants no self-service write: the same
    call shape is allowed on hr and refused on people."""
    people = json.loads(json.dumps(HR).replace("hr___", "people___"))
    people["target"] = "people"
    people = without("employee-updates-own-address", people)
    shared, files = interceptor({"hr": HR, "people": people})
    assert "transformedGatewayRequest" in shared.request(update_address("alice"))["mcp"]
    refused = shared.request(update_address("alice", target="people"))
    assert error(refused) == "UpdateAddress is not permitted for this caller"
    assert [target for target, _ in files.gets] == ["hr", "people"]


def test_other_methods_pass_without_a_policy_file():
    shared, files = interceptor()
    out = shared.request(event("request-alice-views-own-profile") | {"mcp": {"gatewayRequest": {
        "headers": {}, "body": {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}}}})
    assert out["mcp"]["transformedGatewayRequest"]["body"]["method"] == "tools/list"
    assert files.gets == []


def test_a_target_with_no_policy_file_is_not_governed():
    shared, _ = interceptor()
    out = shared.request(tool_call("payroll___update_salary", {"employeeId": "alice"}, ALICE))
    assert error(out) == "tool payroll___update_salary is not governed; no policy covers it"


def test_the_response_of_an_ungoverned_tool_is_withheld():
    shared, _ = interceptor()
    response = event("response-alice-views-own-profile")
    response["mcp"]["gatewayRequest"]["body"]["params"]["name"] = "payroll___get_profile"
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
    out = shared.request(update_address("alice"))
    assert error(out) == "request could not be evaluated: the target's policies could not be loaded"
    response = shared.response(event("response-alice-views-own-profile"))
    assert response["mcp"]["transformedGatewayResponse"]["body"]["error"]["message"] == (
        "response withheld; the target's policies could not be loaded")


def test_a_published_change_takes_effect_after_the_ttl():
    clock = Clock()
    shared, files = interceptor(clock=clock, ttl=60)
    call = update_address("alice")
    assert "transformedGatewayRequest" in shared.request(call)["mcp"]
    files.files["hr"] = without("employee-updates-own-address")
    clock.now = 59
    assert "transformedGatewayRequest" in shared.request(call)["mcp"]
    assert len(files.gets) == 1
    clock.now = 60
    assert error(shared.request(call)) == "UpdateAddress is not permitted for this caller"
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
    call = update_address("alice")
    shared.request(call)
    files.files["hr"] = RuntimeError("throttled")
    clock.now = 600
    assert "transformedGatewayRequest" in shared.request(call)["mcp"]


def test_a_deleted_file_stops_governing_at_the_next_check():
    clock = Clock()
    shared, files = interceptor(clock=clock)
    call = update_address("alice")
    shared.request(call)
    del files.files["hr"]
    clock.now = 600
    assert error(shared.request(call)) == "tool hr___update_address is not governed; no policy covers it"


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
