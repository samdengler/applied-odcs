"""The policy file: what the registry publishes for one Gateway target,
and what the shared interceptor decides with.

One JSON document per target, so a target's policies, tool table, and
contract facts change together:

    {
      "format": 2,
      "target": "hr",
      "resource": "Employee",
      "models": {"Employee":      {"id": "employeeId", "attributes": {"employeeId": "User"}},
                 "AddressChange": {"id": "changeId",   "attributes": {"employeeId": "User"}}},
      "tools": {"hr___update_address": {"action": ..., "id": ..., "input": ..., "payload": "address",
                                        "writes": "homeAddress", "returns": "object",
                                        "model": "AddressChange"}, ...},
      "entities": [<the Contract and Role entities>],
      "policies": "<Cedar text>"
    }

The tool table is the registry's binding of the target's MCP tools to
the contract.  Each tool is one business intent: its action is the
verb the request leg asks, and its model is the contract schema object
its result is, which the response leg filters it as.  resource is the
model a call names on the request leg (Employee::"alice").  A tool
whose payload is the new value of one contract field says so with
writes; the request leg then asks about each leaf at its contract
path, homeAddress.line1, and not as the argument spells it.  The
entities are the contract's tag maps (each field's level and writer,
one pair per model) and any roles the policies read; users come from
the token and records from the response, so neither is in the file.

The verbs follow from the model names: Read<Model> and
Read<Model>Field on the response, and <Verb>Field for the payload of
every tool that has one.  from_folder refuses a descriptor that names
them otherwise.  The token claims the policies read are the Gateway's
identity provider's, the same for every target, so the interceptor
takes them from its environment (handler.py).

from_folder writes a policy file from a use case folder after
cedar-odcs build; it stands in for the registry, and checks the
binding against the contract and the folder's tools.json.  models
reads one back as the UseCases cedar-odcs's handlers take: one for the
request leg and one per model for the response leg.  A format 1 file,
one model for every tool, reads back as format 2.
"""

import importlib.util
import json
from pathlib import Path

import cedarpy
from cedar_odcs.engine.identities import ClaimsMapping
from cedar_odcs.engine.usecase import UseCase

FORMAT = 2
READS = (1, 2)
# The Gateway names each tool <target>___<tool>.
SEPARATOR = "___"
# The entity types a policy file carries.
CARRIED = ("Contract", "Role")


def _verb(name: str) -> str:
    return f'Action::"{name}"'


def _field_verb(action: str) -> str:
    """Action::"UpdateAddress" to Action::"UpdateAddressField"."""
    return action[:-1] + 'Field"'


def verbs(model: str, tools: dict) -> dict:
    """A UseCase's verbs for one model, as the convention gives them."""
    return {
        "read_action": _verb(f"Read{model}"),
        "read_field_action": _verb(f"Read{model}Field"),
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


# ---------------------------------------------------------------- the registry's side

def _module(root: Path):
    spec = importlib.util.spec_from_file_location(f"_binding_{root.name}", root / "usecase.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _schema_leaves(schema: dict) -> set:
    from cedar_odcs.engine.contract import output_schema_paths
    return output_schema_paths(schema)


def check_binding(root, document: dict, contract: str) -> None:
    """The binding against the contract (contract/<contract>.odcs.yaml)
    and, when the folder has one, the Gateway tool schema (tools.json).
    Each model is a schema object of the contract; a tool's outputSchema
    names exactly its model's leaves; a payload a tool writes to a
    contract field names exactly that field's leaves.  Raises
    ValueError naming every difference."""
    root = Path(root)
    problems = []
    leaves = {}
    for model in document["models"]:
        try:
            leaves[model] = _object_leaves(root, contract, model)
        except Exception as e:  # noqa: BLE001  the contract's own error says which
            problems.append(f"model {model}: {e}")
    if document["resource"] not in document["models"]:
        problems.append(f"resource {document['resource']} is not a model")
    for name, tool in document["tools"].items():
        if tool.get("model") not in document["models"]:
            problems.append(f"{name}: model {tool.get('model')!r} is not a model")
        writes = tool.get("writes")
        if writes is not None and "payload" not in tool:
            problems.append(f"{name}: writes {writes} with no payload")
    schemas = root / "tools.json"
    if schemas.is_file():
        by_name = {f"{document['target']}{SEPARATOR}{t['name']}": t for t in json.loads(schemas.read_text())}
        if set(by_name) != set(document["tools"]):
            problems.append(f"tools.json names {sorted(by_name)}; the binding names {sorted(document['tools'])}")
        for name, tool in document["tools"].items():
            schema = by_name.get(name)
            model = tool.get("model")
            if schema is None or model not in leaves:
                continue
            returned = _schema_leaves(schema.get("outputSchema") or {})
            if returned != leaves[model]:
                problems.append(f"{name}: outputSchema and model {model} differ: only in outputSchema "
                                f"{sorted(returned - leaves[model])}, only in the model {sorted(leaves[model] - returned)}")
            writes = tool.get("writes")
            if writes is not None and document["resource"] in leaves:
                argument = schema.get("inputSchema", {}).get("properties", {}).get(tool["payload"], {})
                sent = {f"{writes}.{path}" for path in _schema_leaves(argument)}
                field = {p for p in leaves[document["resource"]] if p.startswith(writes + ".")}
                if not field:
                    problems.append(f"{name}: writes {writes}, which {document['resource']} does not declare")
                elif sent != field:
                    problems.append(f"{name}: payload {tool['payload']} and {writes} differ: only in the payload "
                                    f"{sorted(sent - field)}, only in the contract {sorted(field - sent)}")
    if problems:
        raise ValueError(f"{document['target']}'s binding: " + "; ".join(problems))


def _object_leaves(root: Path, contract: str, model: str) -> set:
    """The leaf paths of one schema object in the contract document, as
    the field rounds name them.  cedar-odcs's leaf_paths reads only the
    object the document is named for."""
    from cedar_odcs.engine.contract import _leaves, contract_path, load_contract
    document = load_contract(contract_path(root, contract).read_text())
    for obj in document.schema_:
        if obj.name == model:
            return {path for path, _ in _leaves(obj.properties, "")}
    raise ValueError(f"the contract has no schema object named {model}")


def from_folder(root) -> dict:
    """The policy file for a use case folder whose build outputs exist.
    A folder whose usecase.py has MODELS binds a model to each tool;
    one without has a single model, the descriptor's resource."""
    from cedar_odcs.cli.main import load_use_case  # the registry's side only

    root = Path(root)
    descriptor = load_use_case(str(root)).USE_CASE
    targets = {name.partition(SEPARATOR)[0] for name in descriptor.tools}
    if len(targets) != 1 or any(SEPARATOR not in name for name in descriptor.tools):
        raise ValueError(f"{descriptor.name}'s tools must all be named <target>{SEPARATOR}<tool> for one target: "
                         f"{', '.join(sorted(descriptor.tools))}")
    expected = verbs(descriptor.resource_type, descriptor.tools)
    named = {key: getattr(descriptor, key) for key in expected}
    if named != expected:
        raise ValueError(f"{descriptor.name} names its verbs {named}; a policy file derives {expected}")
    module = _module(root)
    models = getattr(module, "MODELS", None)
    tools = {name: dict(tool) for name, tool in descriptor.tools.items()}
    if models is None:
        models = {descriptor.resource_type: {"id": descriptor.id_field, "attributes": descriptor.attributes}}
        for tool in tools.values():
            tool["model"] = descriptor.resource_type
    resource = models.get(descriptor.resource_type)
    if resource != {"id": descriptor.id_field, "attributes": descriptor.attributes}:
        raise ValueError(f"{descriptor.name}'s model {descriptor.resource_type} is {resource}; "
                         f"the descriptor says id {descriptor.id_field}, attributes {descriptor.attributes}")
    entities = json.loads((root / "entities.json").read_text())
    document = {
        "format": FORMAT,
        "target": targets.pop(),
        "resource": descriptor.resource_type,
        "models": models,
        "tools": tools,
        "entities": [e for e in entities if e["uid"]["type"] in CARRIED],
        "policies": descriptor.policies,
    }
    contract = getattr(module, "CONTRACT", None)
    if contract is not None:
        check_binding(root, document, contract)
    return document


# ---------------------------------------------------------------- the interceptor's side

def _as_format_2(document: dict) -> dict:
    """A format 1 file: one resource, and every tool returns it."""
    resource = document["resource"]
    model = resource["type"]
    return {
        **document,
        "format": 2,
        "resource": model,
        "models": {model: {"id": resource["id"], "attributes": resource["attributes"]}},
        "tools": {name: {**tool, "model": model} for name, tool in document["tools"].items()},
    }


def _use_case(document: dict, model: str, tools: dict, target: str, claims: ClaimsMapping) -> UseCase:
    spec = document["models"][model]
    return PolicyFileUseCase(
        document["policies"], document["entities"],
        name=target, resource_type=model, id_field=spec["id"], attributes=spec["attributes"],
        tools=tools, claims=claims, **verbs(model, tools),
    )


def models(document: dict, target: str, claims: ClaimsMapping = ClaimsMapping()):
    """A policy file as (request use case, {model: response use case},
    {tool: model}, {action: contract path written}).  Refuses another
    format, another target's file, an unknown model, and policies that
    do not parse, so a bad file fails when it is loaded and not on each
    call."""
    if document.get("format") not in READS:
        raise ValueError(f"policy file format {document.get('format')!r}; this interceptor reads {READS}")
    if document.get("target") != target:
        raise ValueError(f"policy file is for target {document.get('target')!r}, not {target!r}")
    if document["format"] == 1:
        document = _as_format_2(document)
    cedarpy.PolicySet.from_str(document["policies"])
    tools = document["tools"]
    names = set(document["models"])
    unknown = sorted(f"{name}: {tool.get('model')!r}" for name, tool in tools.items() if tool.get("model") not in names)
    if unknown or document["resource"] not in names:
        raise ValueError(f"policy file names a model it does not define: {', '.join(unknown) or document['resource']}")
    request = _use_case(document, document["resource"], tools, target, claims)
    responses = {model: _use_case(document, model, {n: t for n, t in tools.items() if t["model"] == model}, target, claims)
                 for model in names}
    writes = {tool["action"]: tool["writes"] for tool in tools.values() if "writes" in tool}
    return request, responses, {name: tool["model"] for name, tool in tools.items()}, writes


def ungoverned(claims: ClaimsMapping = ClaimsMapping()) -> UseCase:
    """A use case with no tools: its handlers pass every method but
    tools/call and reject every tool, in cedar-odcs's own words."""
    return PolicyFileUseCase("", [], name="ungoverned", resource_type="Ungoverned", id_field="id",
                             attributes={}, tools={}, claims=claims, **verbs("Ungoverned", {}))
