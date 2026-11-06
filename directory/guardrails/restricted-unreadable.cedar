// Guardrail: a field labelled restricted is never allowed, whoever asks,
// whatever the record holds, and whatever the contract's labels are.
@id("guardrail-restricted-unreadable")
forbid(
  principal,
  action == Action::"ReadEmployeeField",
  resource
) when {
  context has field &&
  Contract::"Employee".hasTag(context.field) &&
  Contract::"Employee".getTag(context.field) == "restricted"
};
