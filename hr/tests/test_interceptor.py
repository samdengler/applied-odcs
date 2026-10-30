"""The HR tools through the core handlers: a call is decided on the
request before it is forwarded, on whose record it names and which
fields it sets, and the record the API returns is decided again on the
response, cut to the fields the employee may read."""

import json
from pathlib import Path

from cedar_odcs.engine.calls import call
from cedar_odcs.engine.enforce import Engine
from cedar_odcs.gateway.handlers import handlers
from hr.usecase import TOOLS, USE_CASE

HERE = Path(__file__).parent
request_handler, response_handler = handlers(USE_CASE)

ALICE = json.loads((HERE / "responses" / "alice.json").read_text())


def event(name: str) -> dict:
    return json.loads((HERE / "events" / f"{name}.json").read_text())


def rejection(out: dict) -> str:
    response = out["mcp"]["transformedGatewayResponse"]
    assert response["statusCode"] == 403
    return response["body"]["error"]["message"]


def payload(out: dict) -> dict:
    result = out["mcp"]["transformedGatewayResponse"]["body"]["result"]
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"]
    return result["structuredContent"]


def forwarded(out: dict) -> bool:
    return "transformedGatewayRequest" in out["mcp"]


# ---- what a call names

def test_both_tools_name_the_employee_in_context_input():
    for tool in TOOLS:
        named = call(USE_CASE, tool, {"employeeId": "bob", **({"changes": {"personalPhone": "x"}} if "payload" in TOOLS[tool] else {})})
        assert named.resource == 'Employee::"bob"'
        assert named.context["input"] == {"employeeId": {"__entity": {"type": "User", "id": "bob"}}}


def test_the_token_names_the_caller_and_nothing_else():
    claims = json.loads((HERE / "identities" / "alice.json").read_text())
    projection = Engine(USE_CASE).projection(claims)
    assert projection.principal == 'User::"alice"'
    assert projection.context == {}


# ---- the request leg

def test_an_employee_looking_up_their_own_record_is_forwarded():
    assert forwarded(request_handler(event("request-alice-looks-up-own-record")))


def test_an_employee_looking_up_a_colleague_is_refused_before_the_tool_runs():
    message = rejection(request_handler(event("request-bob-looks-up-alice")))
    assert message == "LookupEmployee is not permitted for this caller"


def test_an_employee_changing_their_own_address_is_forwarded():
    assert forwarded(request_handler(event("request-alice-updates-own-address")))


def test_an_employee_changing_a_colleagues_address_is_refused_at_the_verb():
    message = rejection(request_handler(event("request-alice-updates-bobs-address")))
    assert message == "UpdateEmployee is not permitted for this caller"


def test_an_address_change_carrying_a_raise_is_refused_and_names_the_salary():
    message = rejection(request_handler(event("request-alice-updates-address-and-salary")))
    assert message == "UpdateEmployee rejected; fields not permitted: salary"


def test_a_whole_address_as_one_value_is_refused():
    ev = event("request-alice-updates-own-address")
    ev["mcp"]["gatewayRequest"]["body"]["params"]["arguments"]["changes"] = {"homeAddress": "48 Pine St, Portland"}
    message = rejection(request_handler(ev))
    assert message == "UpdateEmployee rejected; fields not permitted: homeAddress"


# ---- the response leg

def test_the_employee_sees_their_record_without_the_bank_account():
    seen = payload(response_handler(event("response-alice-reads-own-record")))
    assert seen == {key: value for key, value in ALICE.items() if key != "bankAccount"}


def test_the_record_an_update_returns_is_cut_the_same_way():
    seen = payload(response_handler(event("response-alice-updates-own-address")))
    assert seen["homeAddress"]["line1"] == "48 Pine St"
    assert "bankAccount" not in seen


def test_a_colleagues_record_is_withheld_should_the_api_return_one():
    seen = payload(response_handler(event("response-bob-reads-alice")))
    assert seen == {}


# ---- every tool, both legs

BOTH_LEGS = {
    "hr___get_employee": "response-alice-reads-own-record",
    "hr___update_employee": "response-alice-updates-own-address",
}


def test_every_tool_has_both_legs_covered():
    assert set(BOTH_LEGS) == set(TOOLS)


def test_both_legs_for_every_tool():
    for name, fixture in BOTH_LEGS.items():
        ev = event(fixture)
        assert forwarded(request_handler(ev)), name
        assert "bankAccount" not in payload(response_handler(ev)), name
