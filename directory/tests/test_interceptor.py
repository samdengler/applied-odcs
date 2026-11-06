"""The directory through the shared interceptor: every caller gets the
same response, and a field leaves only when the contract labelled it and
not as restricted.  Nothing here names a field's decision by hand except
ssn and the undeclared passportNumber: the expected responses come from
the labels in the policy file, so the tests hold after a relabel."""

import base64
import copy
import json
from pathlib import Path

import pytest
from cedar_odcs.engine.identities import ClaimsMapping
from cedar_odcs.gateway.handlers import TOOL_ERROR

from interceptor.handler import Interceptor, PolicyFiles, Target
from interceptor.policy_file import from_folder

HERE = Path(__file__).parent
LIVE = HERE / "live"
DOCUMENT = from_folder(HERE.parent)
TOOL = "directory___look_up_employee"
RECORD = json.loads((HERE / "responses" / "alice.json").read_text())
SSN = RECORD["ssn"]
COGNITO = ClaimsMapping(subject="username", roles="cognito:groups")


def labels(document: dict = DOCUMENT) -> dict:
    return next(e for e in document["entities"] if e["uid"]["id"] == "Employee")["tags"]


def allowed_by_labels(record: dict, document: dict = DOCUMENT) -> dict:
    tags = labels(document)
    return {k: v for k, v in record.items() if k in tags and tags[k] != "restricted"}


def token(sub: str) -> str:
    encode = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()  # noqa: E731
    return f"Bearer {encode({'alg': 'none'})}.{encode({'sub': sub})}.signature"


def call(sub: str = "alice", employee: str = "alice") -> dict:
    return {"headers": {"Authorization": token(sub)},
            "body": {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                     "params": {"name": TOOL, "arguments": {"employeeId": employee}}}}


def respond(sub: str = "alice", result: dict | None = None, error: dict | None = None, document: dict = DOCUMENT) -> dict:
    body = {"jsonrpc": "2.0", "id": 7, **({"result": result} if result is not None else {}),
            **({"error": error} if error is not None else {})}
    event = {"mcp": {"gatewayRequest": call(sub), "gatewayResponse": {"statusCode": 200, "body": body}}}
    return Target(document, "directory").response_handler(event)["mcp"]["transformedGatewayResponse"]


def text(record) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(record)}]}


def shown(out: dict) -> dict:
    return json.loads(out["body"]["result"]["content"][0]["text"])


# ---- what the policy file holds

def test_the_rule_is_two_policies_and_reads_no_caller_role_or_record():
    assert DOCUMENT["policies"].count("@id(") == 2
    code = "\n".join(line for line in DOCUMENT["policies"].splitlines() if not line.lstrip().startswith("//"))
    assert "principal " not in code and "principal." not in code and "resource." not in code and "Role::" not in code


def test_the_file_has_one_tool_and_the_contracts_labels():
    assert list(DOCUMENT["tools"]) == [TOOL]
    assert labels()["ssn"] == "restricted"
    assert "passportNumber" not in labels()


# ---- the request leg passes everything

@pytest.mark.parametrize("sub", ["alice", "bob"])
def test_every_caller_reaches_the_tool(sub):
    out = Target(DOCUMENT, "directory").request_handler({"mcp": {"gatewayRequest": call(sub)}})
    assert "transformedGatewayRequest" in out["mcp"]


# ---- the response leg, from the labels

def test_a_field_leaves_only_with_a_label_below_restricted():
    assert shown(respond(result=text(RECORD))) == allowed_by_labels(RECORD)
    assert "ssn" not in shown(respond(result=text(RECORD)))


def test_every_caller_gets_the_same_response():
    assert respond("alice", text(RECORD)) == respond("bob", text(RECORD))


def test_the_restricted_field_is_cut_from_both_places_a_result_carries_it():
    out = respond(result={**text(RECORD), "structuredContent": RECORD})
    assert SSN not in json.dumps(out)
    assert out["body"]["result"]["structuredContent"] == allowed_by_labels(RECORD)


def test_a_field_the_contract_does_not_declare_is_cut():
    assert "passportNumber" not in shown(respond(result=text(RECORD)))


def test_a_restricted_value_nested_under_an_undeclared_object_is_cut():
    assert SSN not in json.dumps(respond(result=text({**RECORD, "hr": {"ssn": SSN}})))


def test_a_list_of_restricted_values_under_an_undeclared_name_is_cut():
    assert SSN not in json.dumps(respond(result=text({**RECORD, "history": [{"ssn": SSN}]})))


# ---- what the labels and the policies change

def test_a_new_label_is_the_only_change_needed_to_cut_a_field():
    relabelled = copy.deepcopy(DOCUMENT)
    labels(relabelled)["workEmail"] = "restricted"
    assert "workEmail" in shown(respond(result=text(RECORD)))
    assert "workEmail" not in shown(respond(result=text(RECORD), document=relabelled))


def test_a_later_permit_cannot_open_a_restricted_field():
    later = copy.deepcopy(DOCUMENT)
    later["policies"] += '\n@id("opens-every-field")\npermit(principal, action == Action::"ReadEmployeeField", resource);\n'
    assert shown(respond(result=text(RECORD), document=later)) == allowed_by_labels(RECORD)


def test_without_the_forbid_the_restricted_field_leaves():
    """The forbid is what holds the boundary, and make check proves it is
    in the file: without it the same response carries the ssn."""
    gone = copy.deepcopy(DOCUMENT)
    gone["policies"] = 'permit(principal, action, resource);\n'
    assert shown(respond(result=text(RECORD), document=gone))["ssn"] == SSN


# ---- what the field round cannot decide

def test_a_tools_error_text_does_not_leave():
    out = respond(error={"code": -32001, "message": f"lookup failed for {SSN}", "data": {"ssn": SSN}})
    assert out["body"]["error"] == {"code": -32001, "message": TOOL_ERROR}


def test_a_failed_tools_text_and_stack_trace_do_not_leave():
    """A Lambda function target's failure, as the live Gateway sends it
    (tests/live/live-alice-look_up_employee-000-12-3456.json)."""
    runtime_error = {"errorMessage": f"lookup failed for {SSN}", "errorType": "ValueError",
                     "requestId": "r-1", "stackTrace": [f"handler.py line 23, {SSN}"]}
    out = respond(result={"isError": True, "content": [{"type": "text", "text": json.dumps(runtime_error)}]})
    assert out["statusCode"] == 200
    assert out["body"]["result"] == {"isError": True, "content": [{"type": "text", "text": TOOL_ERROR}]}


def test_content_items_beside_the_record_do_not_leave():
    result = text(RECORD)
    result["content"].append({"type": "resource", "resource": {"uri": "file:///x", "text": f"SSN {SSN}"}})
    out = respond(result=result)
    assert SSN not in json.dumps(out) and len(out["body"]["result"]["content"]) == 1


def test_other_keys_of_the_result_do_not_leave():
    assert SSN not in json.dumps(respond(result={**text(RECORD), "_meta": {"ssn": SSN}}))


def test_text_that_is_not_a_record_is_withheld():
    out = respond(result={"content": [{"type": "text", "text": f"SSN is {SSN}"}]})
    assert SSN not in json.dumps(out) and out["statusCode"] == 403


def test_a_restricted_value_inside_a_labelled_field_does_leave():
    """The filter reads labels and never looks at values.  This is the
    known limit: a value the tool writes into a public field goes with it."""
    assert SSN in shown(respond(result=text({**RECORD, "name": f"Alice ({SSN})"})))["name"]


# ---- one interceptor, two targets

class Files:
    def __init__(self, files: dict):
        self.files = files

    def get(self, target, etag=None):
        return json.dumps(self.files[target]), target


def test_the_same_interceptor_governs_both_targets_from_their_own_files():
    hr = from_folder(HERE.parents[1] / "hr")
    shared = Interceptor(PolicyFiles(Files({"hr": hr, "directory": DOCUMENT})))
    assert "transformedGatewayRequest" in shared.request({"mcp": {"gatewayRequest": call("bob")}})["mcp"]
    other = call("bob")
    other["body"]["params"]["name"] = "hr___get_profile"
    refused = shared.request({"mcp": {"gatewayRequest": other}})["mcp"]["transformedGatewayResponse"]
    assert refused["body"]["error"]["message"] == "ViewProfile is not permitted for this caller"


# ---- live recordings

@pytest.mark.parametrize("path", sorted(LIVE.glob("live-*.json")), ids=lambda p: p.stem)
def test_live_recording_matches_the_shared_interceptor(path):
    """A call recorded through the deployed Gateway, replayed through the
    interceptor with Cognito's claims, gives what the Gateway returned,
    read under the current labels so a relabel does not stale the recording."""
    fixture = json.loads(path.read_text())
    target = Target(DOCUMENT, "directory", COGNITO)
    observed = fixture["observed"]["body"]
    assert SSN not in json.dumps(observed) and "X0000001" not in json.dumps(observed)
    assert "transformedGatewayRequest" in target.request_handler(fixture["request"])["mcp"]
    body = target.response_handler(fixture["response"])["mcp"]["transformedGatewayResponse"]["body"]
    if body["result"].get("isError"):
        assert body == observed
    else:
        recorded = json.loads(observed["result"]["content"][0]["text"])
        assert json.loads(body["result"]["content"][0]["text"]) == allowed_by_labels(recorded)


def test_the_live_recordings_show_the_gateway_handing_over_the_whole_record():
    """The Gateway does not hold a result to the tool's outputSchema: the
    fields the client never saw reached the interceptor, which cut them."""
    fixture = json.loads((LIVE / "live-alice-look_up_employee-alice.json").read_text())
    raw = json.loads(fixture["response"]["mcp"]["gatewayResponse"]["body"]["result"]["content"][0]["text"])
    assert raw["ssn"] == SSN and raw["passportNumber"] == "X0000001"
