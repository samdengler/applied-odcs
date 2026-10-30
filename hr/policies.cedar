// HR: an employee sees their own profile and changes their own
// address, and no one else's.
//
// Each tool is one business intent. get_profile asks ViewProfile and
// returns the Employee model. update_address asks UpdateAddress and
// returns the AddressChange model: the HR API records the change,
// tells payroll, and screens it for payroll diversion. Both tools name
// the employee by employeeId, the token's subject, and the tool table
// (usecase.py) copies it into context.input as a User, so the request
// leg compares it with the caller before the HR API is called. The
// response leg compares the record the API returned,
// resource.employeeId, with the caller again, and cuts it to the
// fields the employee may read.
//
// One permit per question the interceptor asks:
//
//   request leg   ViewProfile              may this caller see this profile?
//                 UpdateAddress            may this caller change this address?
//                 UpdateAddressField       may they set this line? (each one sent)
//   response leg  ReadEmployee             may they see this profile?
//                 ReadEmployeeField        may they see this field? (each one returned)
//                 ReadAddressChange        may they see this change?
//                 ReadAddressChangeField   may they see this field? (each one returned)
//
// Anything no permit allows is refused. No policy names a field: each
// field's level and writer are the contract's
// (contract/employee.odcs.yaml).

// policy0: An employee views their own profile: the call names them.
@id("employee-views-own-profile")
permit(
  principal,
  action == Action::"ViewProfile",
  resource
) when {
  context has input &&
  context.input has employeeId &&
  context.input.employeeId == principal
};

// policy1: An employee changes their own address: the call names them.
@id("employee-updates-own-address")
permit(
  principal,
  action == Action::"UpdateAddress",
  resource
) when {
  context has input &&
  context.input has employeeId &&
  context.input.employeeId == principal
};

// policy2: Each line the call sends is asked at its Employee path,
// homeAddress.line1 and so on, and an employee sets the fields whose
// writer is "owner" on their own record. A line the contract does not
// declare is refused, and so is the call.
@id("employee-sets-own-fields")
permit(
  principal,
  action == Action::"UpdateAddressField",
  resource
) when {
  context has input &&
  context.input has employeeId &&
  context.input.employeeId == principal &&
  context has field &&
  Contract::"Employee/writers".hasTag(context.field) &&
  Contract::"Employee/writers".getTag(context.field) == "owner"
};

// policy3: An employee sees the profile the API returned when it is
// their own.
@id("employee-reads-own-profile")
permit(
  principal,
  action == Action::"ReadEmployee",
  resource
) when {
  resource has employeeId &&
  resource.employeeId == principal
};

// policy4: On their own profile, an employee sees the public and
// confidential fields. The bank account is restricted and stays in the
// payroll portal.
@id("employee-reads-own-profile-fields")
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

// policy5: An employee sees an address change the API returned when it
// is their own.
@id("employee-reads-own-address-change")
permit(
  principal,
  action == Action::"ReadAddressChange",
  resource
) when {
  resource has employeeId &&
  resource.employeeId == principal
};

// policy6: On their own address change, an employee sees the public and
// confidential fields. The fraud score is restricted and stays with the
// fraud team.
@id("employee-reads-own-address-change-fields")
permit(
  principal,
  action == Action::"ReadAddressChangeField",
  resource
) when {
  resource has employeeId &&
  resource.employeeId == principal &&
  context has field &&
  Contract::"AddressChange".hasTag(context.field) &&
  ["public", "confidential"].contains(Contract::"AddressChange".getTag(context.field))
};
