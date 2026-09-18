# provider-egress-policy Specification

## Purpose

Every provider call transmits only explicitly permitted data classes to explicitly permitted providers, denied by default, with secrets excluded always and revocation honored on subsequent calls.

## Requirements

### Requirement: Deny-by-default enforcement boundary
All provider calls — generation, corrective retries, NLU, condensation, embeddings, and evaluation/judge paths — SHALL pass a single enforcement boundary that permits transmission only under an explicit grant and otherwise refuses (never silently downgrades, reroutes, or switches providers). Absence of a grant SHALL deny.

#### Scenario: Ungranted transmission refused
- **WHEN** a provider call has content but no matching grant
- **THEN** it is refused before transmission with a safe code

#### Scenario: No silent fallback
- **WHEN** the granted provider is unavailable
- **THEN** the call fails safely rather than switching to another provider

### Requirement: Data-class grants
Grants SHALL identify permitted data classes, recipient providers, and purpose. Classified content (prompts, history, company documents/code/resolutions, live results, embeddings, telemetry, Debug data) SHALL inherit the strictest applicable restriction on mixed requests. Grant checks SHALL consider locality and revocation state before sending.

#### Scenario: Mixed request inherits strictness
- **WHEN** a request mixes public and company content
- **THEN** the company-content restriction governs the whole transmission

#### Scenario: Revoked grant denies
- **WHEN** a grant is revoked
- **THEN** subsequent calls are refused without restart or redeploy

### Requirement: Secret exclusion
Secrets, credentials, API keys, and transport headers SHALL be excluded from every provider payload regardless of ordinary content approval. Transport authentication material SHALL NOT enter model context.

#### Scenario: Secrets never transmitted
- **WHEN** payloads are inspected across all provider paths, including retries and evaluation
- **THEN** no secret or credential material is present even when the surrounding content is permitted

### Requirement: Synthetic-marker test harness
Every provider boundary SHALL be instrumented in tests with synthetic sensitive-data markers covering generation, retries, NLU, condensation, embeddings, and evaluation/judge paths. Markers SHALL prove deny-by-default, grant, and revoke behavior per path without using real credentials or private data and without authorizing any paid call.

#### Scenario: Marker coverage per path
- **WHEN** the harness runs against a provider path with marked synthetic content
- **THEN** deny, grant, and revoke outcomes are each demonstrated and no marker escapes to a real provider

### Requirement: Provider compatibility conformance
Each selected generation provider SHALL conform to bounded inputs/outputs, model/capability identity, errors, timeouts, cancellation/streaming, and locality behavior; each embedding change SHALL satisfy model/revision/dimension/metric compatibility. Conformance SHALL be evidenced per provider, not inferred from one successful call.

#### Scenario: Per-provider evidence
- **WHEN** a provider is selected for use
- **THEN** its conformance checks pass for that provider before it serves traffic
