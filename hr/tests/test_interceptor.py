"""The HR tools through the shared interceptor's handlers for this
folder's policy file: a call is decided on the request before it is
forwarded, on whose record it names and each address line it sends,
and each tool's result is decided on the response as its own model,
cut to the fields the employee may read."""

import json
from pathlib import Path

from cedar_odcs.engine.calls import call
from cedar_odcs.engine.enforce import Engine
from hr.usecase import TOOLS, USE_CASE
from interceptor.handler import Target
from interceptor.policy_file import from_folder

HERE = Path(__file__).parent
HR = Target(from_folder(HERE.parent), "hr")

PROFILE = json.loads((HERE / "responses" / "alice.json").read_text())
CHANGE = json.loads((HERE / "responses" / "alice-address-change.json").read_text())


def event(name: str) -> dict:
    return json.loads((HERE / "events" / f"{name}.json").read_text())


def request(name: str) -> dict:
    return HR.request_handler(event(name))


def response(name: str) -> dict:
    return HR.response_handler(event(name))


def rejection(out: dict) -> str:
    result = out["mcp"]["transformedGatewayResponse"]
    assert result["statusCode"] == 403
    return result["body"]["error"]["message"]


def payload(out: dict) -> dict:
    result = out["mcp"]["transformedGatewayResponse"]["body"]["result"]
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"]
    return result["structuredContent"]


def forwarded(out: dict) -> bool:
    return "transformedGatewayRequest" in out["mcp"]


# ---- what a call names

def test_both_tools_name_the_employee_in_context_input():
    for tool in TOOLS:
        named = call(USE_CASE, tool, {"employeeId": "bob", **({"address": {"line1": "x"}} if "payload" in TOOLS[tool] else {})})
        assert named.resource == 'Employee::"bob"'
        assert named.context["input"] == {"employeeId": {"__entity": {"type": "User", "id": "bob"}}}


def test_the_token_names_the_caller_and_nothing_else():
    claims = json.loads((HERE / "identities" / "alice.json").read_text())
    projection = Engine(USE_CASE).projection(claims)
    assert projection.principal == 'User::"alice"'
    assert projection.context == {}


def test_each_tool_returns_its_own_model():
    assert {name: tool["model"] for name, tool in TOOLS.items()} == {
        "hr___get_profile": "Employee", "hr___update_address": "AddressChange"}


# ---- the request leg

def test_an_employee_viewing_their_own_profile_is_forwarded():
    assert forwarded(request("request-alice-views-own-profile"))


def test_an_employee_viewing_a_colleague_is_refused_before_the_tool_runs():
    assert rejection(request("request-bob-views-alice")) == "ViewProfile is not permitted for this caller"


def test_an_employee_changing_their_own_address_is_forwarded():
    assert forwarded(request("request-alice-updates-own-address"))


def test_an_employee_changing_a_colleagues_address_is_refused_at_the_verb():
    assert rejection(request("request-alice-updates-bobs-address")) == "UpdateAddress is not permitted for this caller"


def test_each_address_line_is_decided_at_its_contract_path():
    message = rejection(request("request-alice-sends-salary-in-address"))
    assert message == "UpdateAddress rejected; fields not permitted: homeAddress.salary"


def test_the_forwarded_call_is_the_call_as_sent():
    ev = event("request-alice-updates-own-address")
    out = HR.request_handler(ev)
    assert out["mcp"]["transformedGatewayRequest"]["body"] == ev["mcp"]["gatewayRequest"]["body"]


# ---- the response leg, one model per tool

def test_the_profile_comes_back_without_the_bank_account():
    assert payload(response("response-alice-views-own-profile")) == {
        key: value for key, value in PROFILE.items() if key != "bankAccount"}


def test_the_address_change_comes_back_without_the_fraud_score():
    assert payload(response("response-alice-updates-own-address")) == {
        key: value for key, value in CHANGE.items() if key != "fraudScore"}


def test_a_colleagues_profile_is_withheld_should_the_api_return_one():
    assert payload(response("response-bob-views-alice")) == {}


def test_a_profile_returned_by_update_address_is_withheld():
    """The model is the tool's, whatever comes back: an Employee record
    from update_address has no changeId, the id of an AddressChange, so
    nothing of it is shown."""
    ev = event("response-alice-updates-own-address")
    result = ev["mcp"]["gatewayResponse"]["body"]["result"]
    result["structuredContent"] = PROFILE
    result["content"][0]["text"] = json.dumps(PROFILE)
    assert payload(HR.response_handler(ev)) == {}
