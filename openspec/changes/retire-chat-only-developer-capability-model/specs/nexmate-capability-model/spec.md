## Purpose

Defines how NexMate determines which of its own capabilities an authenticated
Frappe user may exercise — Employee or Developer — and, critically, the boundary
that capability gates. Capability decides which NexMate features exist for a
user; it never decides which ERPNext business records that user may read, which
remains exclusively Frappe-native authorization. Capability is also distinct from
the authority to configure NexMate behaviour: holding Developer capability never
confers configuration authority.

## ADDED Requirements

### Requirement: Capability is derived from real Frappe roles

The control plane SHALL derive a NexMate capability for each authenticated request
from that user's **actual** Frappe roles, evaluated against server-managed
configuration that names real Frappe roles. A user holding a configured role
SHALL be assigned the `developer` capability; every other authenticated user
SHALL be assigned `employee`. The Frappe Role store SHALL remain the sole source
of truth for role membership. NexMate SHALL NOT introduce a second user, role or
membership store, and SHALL NOT cache a user's roles, capability or any
authorization grant across requests.

The configured role list SHALL be resolved with the following precedence.
A `developer_roles` value configured in `NexMate Settings` takes precedence
over the existing `site_config` developer-role configuration when it names one
or more roles. When the Settings value is absent or unconfigured — proven by
the store, never inferred from a failed read — derivation SHALL fall back to
the `site_config` configuration. When the Settings value is explicitly
configured as an empty list, no Developer roles are granted. When the Settings
record is proven saved yet cannot be read, or the role rows cannot be read, or
the store itself cannot be read, derivation SHALL fail closed to `employee`
with NO fallback to `site_config`: an unreadable configuration is a failure,
not absence. Role resolution SHALL remain live and per-request; no NexMate
role cache SHALL be introduced, so role grants, revocations and deletions take
effect on the next request.

#### Scenario: Configured role confers developer capability

- **WHEN** an authenticated user's actual Frappe roles include a role named in the
  server-managed developer-role configuration
- **THEN** the request is assigned the `developer` capability

#### Scenario: Unconfigured user receives employee capability

- **WHEN** an authenticated user holds no configured role
- **THEN** the request is assigned the `employee` capability

#### Scenario: Role is not administrator

- **WHEN** a user holds the `developer` capability together with ordinary
  business roles, and Frappe denies that user a specific ERPNext business record
- **THEN** NexMate denies that record exactly as it would for any other user

#### Scenario: No implicit elevation

- **WHEN** a user is a System Manager or Administrator but holds no configured
  developer role
- **THEN** the request is assigned the `employee` capability

#### Scenario: Capability is re-derived per request

- **WHEN** the same site is asked for two metadata authorization decisions for two
  different users
- **THEN** each decision derives that user's capability from live Frappe roles at
  the time of the decision and neither observes the other's result

#### Scenario: Configured Settings roles take precedence

- **WHEN** `NexMate Settings` names one or more developer roles
- **THEN** derivation uses the Settings value rather than the `site_config`
  developer-role configuration

#### Scenario: Absent Settings roles fall back to site configuration

- **WHEN** the Settings record was never saved, so `NexMate Settings` carries
  no developer-role configuration
- **THEN** derivation uses the existing `site_config` developer-role
  configuration unchanged

#### Scenario: Unreadable Settings roles fail closed without fallback

- **WHEN** the Settings record was saved but cannot be read, the role rows
  cannot be read, or the store itself cannot be read
- **THEN** derivation fails closed to `employee` with no fallback to
  `site_config`, and the failure is logged distinctly from a malformed
  mapping

#### Scenario: Explicitly empty Settings roles grant nothing

- **WHEN** `NexMate Settings` is explicitly configured with an empty developer-role
  list
- **THEN** no user derives the `developer` capability from that configuration

#### Scenario: Deleted roles never grant capability

- **WHEN** a configured role name no longer exists as a Frappe Role
- **THEN** it matches no user and grants nothing, with no restart or cache flush
  required for the removal to take effect

### Requirement: Capability derivation fails closed

Capability derivation SHALL fail closed. If the role configuration is malformed,
not a list, contains non-string or otherwise invalid entries, or the live role
lookup fails, the request SHALL be assigned the least-privileged capability
without elevation. A derivation failure SHALL NOT silently fall back to
`developer`, SHALL NOT be reported to the user as an authorization grant, and
SHALL NOT widen any access. No browser-supplied field SHALL influence derivation.

#### Scenario: Malformed role configuration

- **WHEN** the configured developer-role list is not a list of valid role names
- **THEN** derivation fails closed to `employee` without elevation

#### Scenario: Role lookup failure

- **WHEN** the live role lookup for the session user raises an error
- **THEN** derivation fails closed to `employee` and the request proceeds without
  developer capability

#### Scenario: Forged capability refused

- **WHEN** a caller supplies a capability, mode or role field
- **THEN** the request is refused and the supplied value is ignored entirely

### Requirement: Role changes take effect on the next request

Because capability is re-derived from live Frappe state on every request, a role
grant SHALL take effect on the next request and a role revocation SHALL remove
the capability on the next request, with no restart, cache flush or NexMate-side
invalidation step.

#### Scenario: Role added

- **WHEN** a configured developer role is added to a user
- **THEN** that user's next request is assigned the `developer` capability

#### Scenario: Role removed

- **WHEN** a configured developer role is removed from a user
- **THEN** that user's next request is no longer assigned the `developer`
  capability and developer-only features are unavailable

### Requirement: Capability never widens ERPNext business-record authorization

The capability SHALL govern only which NexMate features are available. It SHALL
NOT grant, widen, cache or hint at ERPNext business-record authorization. Every
ERPNext business-record read SHALL be decided solely by Frappe-native
authorization against the live session user, on every read, regardless of
capability. A capability that permits a NexMate feature SHALL never cause a
record the Frappe permission engine denies to be returned, and a capability
SHALL NOT be recorded, cached or reused as an authorization grant.

#### Scenario: Developer still bound by Frappe permissions

- **WHEN** a `developer`-capability user requests a business record Frappe denies
- **THEN** the read is refused and no field of that record is returned

#### Scenario: Employee and developer read identically

- **WHEN** the same session user performs the same authorized business read under
  both capabilities
- **THEN** the authorized result is identical

#### Scenario: Capability is not an authorization grant

- **WHEN** a capability check succeeds
- **THEN** no business-record permission is thereby established, and the
  subsequent read still re-derives authorization from Frappe

### Requirement: Capability is distinct from configuration authority

Holding the `developer` capability SHALL NOT confer authority to configure NexMate
behaviour, and authority to configure NexMate SHALL NOT by itself confer the
`developer` capability. These are separate controls with separate authorities.

A capability-gated feature may additionally be governed by an
administrator-controlled policy stored by NexMate. For such a feature, the
capability decides whether the user may exercise the feature at all, and the
policy decides which objects the feature may act on. Both SHALL be evaluated, and
neither SHALL substitute for the other.

Modifying such a policy SHALL require normal Frappe write permission on the
configuration record. NexMate SHALL NOT create a bespoke role to express this
separation, and SHALL NOT grant policy-edit rights by virtue of a capability.

#### Scenario: Developer cannot configure the policy

- **WHEN** a user holds the `developer` capability but not write permission on the
  configuration record
- **THEN** that user cannot modify the policy

#### Scenario: Configuration authority does not grant capability

- **WHEN** a user may write the configuration record but holds no configured
  developer role
- **THEN** that user is still assigned the `employee` capability and is refused
  capability-gated features

#### Scenario: Both controls are evaluated

- **WHEN** a capability-gated feature is governed by an administrator policy
- **THEN** the request is permitted only if the capability permits the feature and
  the policy permits the requested object

### Requirement: Capability is carried on the wire as the existing mode field

The gateway envelope SHALL carry the derived capability in the existing `mode`
field. NexMate SHALL NOT introduce a second envelope field asserting the same
fact. The envelope value is untrusted on the consumer side and SHALL be validated
for shape only; it SHALL NOT be used as an authorization input by the inference
service. Browser mode or capability fields SHALL be refused rather than accepted
and ignored, so the caller cannot select its own capability.

#### Scenario: No duplicate capability field

- **WHEN** the gateway envelope is constructed
- **THEN** it carries the derived capability once, in the existing `mode` field,
  and no additional capability field exists

#### Scenario: Browser mode refused

- **WHEN** a browser supplies a mode or capability field
- **THEN** the request is refused as an unsupported field and no upstream call is
  made

#### Scenario: Envelope value is not an authorization input

- **WHEN** inference receives an envelope carrying a capability value
- **THEN** it uses that value only to shape its own behaviour and never to
  authorize a metadata or business-record operation
