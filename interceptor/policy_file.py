"""The policy file: what the registry publishes for one Gateway target,
and what the shared interceptor decides with.

One JSON document per target, so a target's policies, tool table, and
contract facts change together:

    {
      "format": 1,
      "target": "hr",
      "resource": {"type": "Employee", "id": "employeeId",
                   "attributes": {"employeeId": "User", "manager": "User"}},
      "tools": {"hr___update_employee": {"action": ..., "id": ..., "input": ...,
                                         "payload": ..., "returns": ...}, ...},
      "entities": [<the Contract and Role entities>],
      "policies": "<Cedar text>"
    }

The tool table is the registry's binding of the target's MCP tools to
the contract.  resource says how a row the tool returns becomes a Cedar
entity.  The entities are the contract's tag maps (each field's level
and writer) and the role hierarchy; users come from the token and
records from the response, so neither is in the file.

The verbs follow from the resource type: Read<Type> and
Read<Type>Field on the response, and <Verb>Field for the payload of
every tool that has one.  from_folder refuses a descriptor that names
them otherwise.  The token claims the policies read are the Gateway's
identity provider's, the same for every target, so the interceptor
takes them from its environment (handler.py).

from_folder writes a policy file from a use case folder after
cedar-odcs build; it stands in for the registry.  use_case reads one
back as the UseCase cedar-odcs's handlers take, with the policies and
entities held in memory.
"""

import json
from pathlib import Path

import cedarpy
from cedar_odcs.engine.identities import ClaimsMapping
from cedar_odcs.engine.usecase import UseCase

FORMAT = 1
# The Gateway names each tool <target>___<tool>.
SEPARATOR = "___"
# The entity types a policy file carries.
CARRIED = ("Contract", "Role")


def _verb(name: str) -> str:
    return f'Action::"{name}"'


def _field_verb(action: str) -> str:
    """Action::"UpdateEmployee" to Action::"UpdateEmployeeField"."""
    return action[:-1] + 'Field"'


def verbs(resource_type: str, tools: dict) -> dict:
    """The descriptor's verbs, as the convention gives them."""
    return {
        "read_action": _verb(f"Read{resource_type}"),
        "read_field_action": _verb(f"Read{resource_type}Field"),
        "field_actions": {tool["action"]: _field_verb(tool["action"]) for tool in tools.values() if "payload" in tool},
    }


class PolicyFileUseCase(UseCase):
    """A UseCase whose policies and entities come from a policy file,
    not from files under a root."""

    def __init__(self, policies: str, entities: list, **descriptor):
        super().__init__(root=None, **descriptor)
        self._policies = policies
        self._entities = entities

    @property
    def policies(self) -> str:
        return self._policies

    @property
    def entities(self) -> list:
        return self._entities


def from_folder(root) -> dict:
    """The policy file for a use case folder whose build outputs exist."""
    from cedar_odcs.cli.main import load_use_case  # the registry's side only

    descriptor = load_use_case(str(root)).USE_CASE
    targets = {name.partition(SEPARATOR)[0] for name in descriptor.tools}
    if len(targets) != 1 or any(SEPARATOR not in name for name in descriptor.tools):
        raise ValueError(f"{descriptor.name}'s tools must all be named <target>{SEPARATOR}<tool> for one target: "
                         f"{', '.join(sorted(descriptor.tools))}")
    expected = verbs(descriptor.resource_type, descriptor.tools)
    named = {key: getattr(descriptor, key) for key in expected}
    if named != expected:
        raise ValueError(f"{descriptor.name} names its verbs {named}; a policy file derives {expected}")
    entities = json.loads((Path(root) / "entities.json").read_text())
    return {
        "format": FORMAT,
        "target": targets.pop(),
        "resource": {"type": descriptor.resource_type, "id": descriptor.id_field,
                     "attributes": descriptor.attributes},
        "tools": descriptor.tools,
        "entities": [e for e in entities if e["uid"]["type"] in CARRIED],
        "policies": descriptor.policies,
    }


def use_case(document: dict, target: str, claims: ClaimsMapping = ClaimsMapping()) -> UseCase:
    """A policy file as a UseCase.  Refuses another format, another
    target's file, and policies that do not parse, so a bad file fails
    when it is loaded and not on each call."""
    if document.get("format") != FORMAT:
        raise ValueError(f"policy file format {document.get('format')!r}; this interceptor reads {FORMAT}")
    if document.get("target") != target:
        raise ValueError(f"policy file is for target {document.get('target')!r}, not {target!r}")
    cedarpy.PolicySet.from_str(document["policies"])
    resource, tools = document["resource"], document["tools"]
    return PolicyFileUseCase(
        document["policies"], document["entities"],
        name=target, resource_type=resource["type"], id_field=resource["id"],
        attributes=resource["attributes"], tools=tools, claims=claims,
        **verbs(resource["type"], tools),
    )


def ungoverned(claims: ClaimsMapping = ClaimsMapping()) -> UseCase:
    """A use case with no tools: its handlers pass every method but
    tools/call and reject every tool, in cedar-odcs's own words."""
    return PolicyFileUseCase("", [], name="ungoverned", resource_type="Ungoverned", id_field="id",
                             attributes={}, tools={}, claims=claims, **verbs("Ungoverned", {}))
