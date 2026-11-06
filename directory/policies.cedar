// The directory: a field labelled restricted never leaves.
//
// These two statements are the whole policy.  Neither reads the caller,
// a role, or the record, so they need one piece of metadata: the level
// the contract gives each field (contract/employee.odcs.yaml).

// Every call and every record passes.  Later policies replace this one
// with narrower permits as roles and owners become available.
@id("everything-else-passes")
permit(principal, action, resource);

// A field leaves only when the contract labelled it, and not as
// restricted.  A forbid overrides every permit, so no later permit can
// open a restricted field or a field the contract does not declare.
@id("restricted-never-leaves")
forbid(principal, action == Action::"ReadEmployeeField", resource)
unless {
  context has field &&
  Contract::"Employee".hasTag(context.field) &&
  Contract::"Employee".getTag(context.field) != "restricted"
};
