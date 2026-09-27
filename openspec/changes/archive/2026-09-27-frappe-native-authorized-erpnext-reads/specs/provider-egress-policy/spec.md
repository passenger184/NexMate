## ADDED Requirements

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
