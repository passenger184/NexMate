## ADDED Requirements

### Requirement: Frappe-authorized tool execution on every entry point
Every tool execution path, including replacements for legacy/direct `/tools/*` endpoints, SHALL require Frappe-derived identity/site/permission and durable proposal approval before execution, never client-supplied mode, LLM classification, or post-execution filtering. The gateway envelope SHALL be validated like chat envelopes, and execution SHALL recheck authorization immediately before acting. Use of a durable proposal on an unauthorized site or by a non-owner SHALL be refused before retrieval or execution.

#### Scenario: Unauthorized tool path refused before execution
- **WHEN** a caller presents a durable proposal owned by another user or bound to another site
- **THEN** Frappe refuses before any tool invocation, with no state change and with the denial audited

#### Scenario: Legacy direct tool replacement requires durable approval
- **WHEN** a legacy direct `/tools/*` call is replayed without a Frappe persistent proposal and explicit approval
- **THEN** it is refused before execution, even with a valid service credential, and the caller is directed to the Frappe durable flow

