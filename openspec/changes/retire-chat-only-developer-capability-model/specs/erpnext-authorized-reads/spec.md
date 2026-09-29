## MODIFIED Requirements

### Requirement: NexMate may narrow but never widen access
The NexMate layer SHALL only further restrict what the Frappe permission engine authorizes. Effective ERPNext access SHALL equal Frappe-authorized access intersected with NexMate-allowed access. No NexMate policy, configuration, role mapping, capability, mode, metadata access policy, numeric operational limit, cache, or convenience behavior SHALL expand access beyond what the Frappe permission engine authorizes for the session user. Authorization SHALL be re-derived per read against live Frappe state; NexMate SHALL NOT cache or reuse an authorization grant across requests. This requirement governs **business records**. It SHALL NOT be read to prohibit a NexMate capability, or an administrator-controlled metadata access policy, from gating access to DocType **metadata**, which contains no business record data and is not subject to business-record permission; metadata access remains separately specified, is gated in the control plane by capability and by the site's administrator-controlled metadata access policy, and is served with a minimized projection. Neither the capability nor the metadata policy SHALL confer, imply or cache business-record authorization.

#### Scenario: NexMate policy cannot expand access
- **WHEN** a NexMate policy would permit an operation or field the Frappe permission engine denies
- **THEN** the denial holds and access is not expanded

#### Scenario: Authorization is re-derived per read
- **WHEN** a user's Frappe permissions are narrowed between two reads
- **THEN** the later read reflects the narrowed permissions without requiring a restart or a NexMate-side cache flush

#### Scenario: Business-record rule does not govern metadata capability
- **WHEN** capability or the administrator-controlled metadata access policy gates DocType metadata access rather than a business record
- **THEN** that gating is not a violation of this requirement, provided no business record is returned and business-record authorization is unchanged

#### Scenario: Metadata never returns business data
- **WHEN** DocType metadata is served under capability and policy
- **THEN** the response contains structural field attributes only and no business record values, rows, Select or Link field option values, or the DocType permission table

#### Scenario: Metadata policy confers no business-record access
- **WHEN** a DocType is permitted by the site's metadata access policy
- **THEN** no permission to read any record of that DocType is thereby established, and a later business read of that DocType is still decided by Frappe-native authorization

#### Scenario: Numeric limits narrow only, never widen
- **WHEN** an administrator configures a numeric operational limit inside its supported range
- **THEN** the limit constrains how much authorized data one request may return and never permits data Frappe denies, a DocType or field outside the allowlists, or a value above the immutable service ceiling

### Requirement: Mode is not ERPNext authorization
The existing developer and employee personas SHALL be retained and SHALL continue to control prompt, knowledge-retrieval scope, code-tool availability, and other existing NexMate capabilities. Capability SHALL NOT determine ERPNext **business-record** authorization. Both capabilities SHALL read ERPNext business data exclusively through the same Frappe-native authorization boundary, and the same session user SHALL receive the same authorized ERPNext result in either capability.

The prohibition is specifically on capability determining which **business records** a user may read. It is not a prohibition on capability determining which **NexMate features** exist. Capability MAY gate a NexMate feature that returns no business record data, such as DocType metadata. Such a gate SHALL be enforced in the Frappe control plane against the live session user, SHALL NOT be re-derived or widened by inference, and SHALL NOT confer, imply or cache any business-record permission. In particular, the `developer` capability SHALL NOT be treated as administrator, SHALL NOT bypass Frappe authorization, and SHALL NOT cause a business record the Frappe permission engine denies to be returned.

The separate, administrator-controlled metadata access policy SHALL be evaluated only after capability, SHALL never substitute for capability, and SHALL never widen any access that the business-record boundary would deny. A metadata response SHALL contain no business values, no rows, no field option values, and no `permissions` table. The business-record authorization boundary, its re-derivation, its minimization and its anti-oracle behavior are unchanged by this change.

#### Scenario: Mode does not change row authorization
- **WHEN** the same session user performs the same business read with the developer capability and with the employee capability
- **THEN** the authorized ERPNext result is identical

#### Scenario: Mode capabilities unchanged
- **WHEN** a read is requested under either capability
- **THEN** existing per-capability restrictions on prompts, retrieval scope, and code tools are unchanged

#### Scenario: Developer capability does not bypass Frappe
- **WHEN** a developer-capability user requests a business record Frappe denies that user
- **THEN** the read is refused and no field of the record is returned

#### Scenario: Capability may gate a non-record feature
- **WHEN** a capability gates access to a NexMate feature that returns no business record data
- **THEN** the gate is permitted and does not alter business-record authorization

#### Scenario: Metadata policy narrows only, never widens
- **WHEN** the administrator narrows the metadata access policy
- **THEN** metadata access narrows and no previously denied business-record access is granted, because the policy governs metadata only
