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

### Requirement: Authorized ERPNext business data is a classified local-default data class
Authorized ERPNext business records returned to the user SHALL be classified as a local-default data class, alongside company documents, source code, resolved issues, live ERP results, document/page context, prompts, and conversation history. Once that data crosses the Frappe-to-inference boundary it is subject to the same deny-by-default all-call egress policy as any other sensitive content, and it SHALL NOT be treated as public or shareable merely because it was already Frappe-authorized for the requesting user. Authorization for one user SHALL NOT constitute consent to disclose that data to any provider, recipient, or purpose. A mixed request that contains authorized ERPNext business data SHALL inherit the restrictions of its most sensitive content, and the classification SHALL cover every provider path that can carry the data, including generation, corrective retries, NLU, condensation, embeddings, and evaluation/judge paths. ERPNext credentials SHALL remain excluded from provider payloads and SHALL never be carried in the authorized context. No new provider, recipient, or cloud grant is introduced by this change, and an existing configuration SHALL NOT be treated as consent.

#### Scenario: Authorized data is not public by virtue of authorization
- **WHEN** ERPNext business data has been authorized for a user by Frappe
- **THEN** it is still classified local-default and is not eligible for cloud disclosure without an explicit approved policy for that data class, provider, and purpose

#### Scenario: Mixed request inherits the strictest restriction
- **WHEN** one turn carries both authorized ERPNext business data and other content
- **THEN** the whole request is treated under the restrictions of the most sensitive content present

#### Scenario: Credentials excluded from the authorized context
- **WHEN** the authorized context is constructed and later passed toward a provider path
- **THEN** it contains no ERPNext credential, and credentials remain excluded regardless of content approval

#### Scenario: Configuration is not consent
- **WHEN** a provider or credential is configured in the environment
- **THEN** that configuration alone does not authorize transmission of authorized ERPNext business data and does not create a grant
