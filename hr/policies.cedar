// HR: an employee reads and changes their own record, and no one
// else's.
//
// The record is the employee. Its id, employeeId, is the employee's
// own user id, the token's subject. Both tools name the record by that
// argument, and the tool table (usecase.py) copies it into
// context.input as a User, so the request leg compares it with the
// caller before the HR API is called. The response leg compares the
// record the API returned, resource.employeeId, with the caller again,
// and cuts the record to the fields the employee may read.
//
// One permit per question the interceptor asks:
//
//   request leg   LookupEmployee       may this caller look up this record?
//                 UpdateEmployee       may this caller change this record?
//                 UpdateEmployeeField  may they set this field? (each one sent)
//   response leg  ReadEmployee         may they see this record?
//                 ReadEmployeeField    may they see this field? (each one returned)
//
// Anything no permit allows is refused. No policy names a field: each
// field's level and writer are the contract's
// (contract/employee.odcs.yaml).

// policy0: An employee looks up their own record: the call names them.
@id("employee-looks-up-own-record")
permit(
  principal,
  action == Action::"LookupEmployee",
  resource
) when {
  context has input &&
  context.input has employeeId &&
  context.input.employeeId == principal
};

// policy1: An employee changes their own record: the call names them.
@id("employee-updates-own-record")
permit(
  principal,
  action == Action::"UpdateEmployee",
  resource
) when {
  context has input &&
  context.input has employeeId &&
  context.input.employeeId == principal
};

// policy2: On their own record, an employee sets the fields whose
// writer is "owner": the home address and the personal phone.
@id("employee-sets-own-fields")
permit(
  principal,
  action == Action::"UpdateEmployeeField",
  resource
) when {
  context has input &&
  context.input has employeeId &&
  context.input.employeeId == principal &&
  context has field &&
  Contract::"Employee/writers".hasTag(context.field) &&
  Contract::"Employee/writers".getTag(context.field) == "owner"
};

// policy3: An employee sees the record the API returned when it is
// their own.
@id("employee-reads-own-record")
permit(
  principal,
  action == Action::"ReadEmployee",
  resource
) when {
  resource has employeeId &&
  resource.employeeId == principal
};

// policy4: On their own record, an employee sees the public and
// confidential fields. The bank account is restricted and stays in the
// payroll portal.
@id("employee-reads-own-fields")
permit(
  principal,
  action == Action::"ReadEmployeeField",
  resource
) when {
  resource has employeeId &&
  resource.employeeId == principal &&
  context has field &&
  Contract::"Employee".hasTag(context.field) &&
  ["public", "confidential"].contains(Contract::"Employee".getTag(context.field))
};
