// Guardrail: a field request with no field named, or naming a field the
// contract does not declare, is never allowed.
@id("guardrail-fail-closed")
forbid(
  principal,
  action == Action::"ReadEmployeeField",
  resource
) when {
  !(context has field && Contract::"Employee".hasTag(context.field))
};
