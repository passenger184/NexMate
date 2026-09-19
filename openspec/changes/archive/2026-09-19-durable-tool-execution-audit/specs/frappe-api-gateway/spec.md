## ADDED Requirements

### Requirement: Durable tool proposal and approval via Frappe
Frappe SHALL expose authenticated, whitelisted methods to create, approve, reject, and query durable tool proposals for business writes and code edits, using standard Frappe authentication and session CSRF checks. Creation SHALL persist an immutable actor/site-bound proposal as defined in `durable-tool-execution` (exact payload/diff, target, reason, expiry, preconditions, correlation). Approval and rejection SHALL be explicit, durable, actor-bound, and require the same authentication; browser-supplied actor/site or direct inference proposal creation SHALL be refused. Execution SHALL only occur after Frappe authorization, permission recheck, and approval validity checks, and SHALL be performed through the separate confined executor for code. Direct browser-to-inference tool, proposal, or approval calls SHALL remain impossible.

#### Scenario: Durable proposal created via Frappe
- **WHEN** an authenticated Frappe user creates a business-write proposal with an exact payload, target, and reason
- **THEN** Frappe persists the immutable proposal with actor/site/expiry/correlation and returns the proposal identifier without executing it

#### Scenario: Approval required before execution
- **WHEN** a proposal exists but has not been explicitly approved by an authorized actor
- **THEN** any execution attempt is refused before tool invocation, even with a valid gateway envelope

#### Scenario: Direct inference proposal bypass refused
- **WHEN** a browser attempts to create or approve a proposal by calling inference directly
- **THEN** the request never reaches inference and no durable proposal is created or approved

### Requirement: Durable execution outcome correlation
Frappe SHALL correlate execution attempts and outcomes to the same proposal and audit ledger entry by correlation/request/action identifiers, including successes, denials, failures, and uncertain outcomes. Clients SHALL be able to query the proposal and its correlated audit state through Frappe, without gaining direct inference audit-store access.

#### Scenario: Outcome queryable through Frappe
- **WHEN** an observer queries a proposal identifier through Frappe after execution, denial, or uncertain-outcome reconciliation
- **THEN** Frappe returns the linked audit outcome (success/denied/failed/uncertain) with actor/site/timestamp, without exposing the underlying inference audit store directly
