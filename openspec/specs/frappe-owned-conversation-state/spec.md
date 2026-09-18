# frappe-owned-conversation-state Specification

## Purpose

Conversation history becomes durable state owned by Frappe: each thread belongs to one authenticated user on one site, survives inference restarts, and is the only history the gateway may use.

## Requirements

### Requirement: Owned conversation records
Frappe SHALL persist every multi-turn thread as a conversation record carrying the owning user's identity, the site where it was created, the derived persona, and creation/update timestamps. Records SHALL be readable, extendable, and deletable only by their owner on the same site through the gateway methods; no caller-supplied identifier SHALL substitute for that ownership check. Ownership SHALL derive from the authenticated Frappe session, never from browser parameters. Privileged Frappe roles SHALL NOT bypass the NexMate API owner check; administrative DocType access outside the NexMate API is a separate concern and confers no gateway continuity.

#### Scenario: Thread persists across restarts
- **WHEN** an authenticated user chats, the inference service restarts, and the user continues the thread
- **THEN** the earlier turns are still present because they live in the Frappe-owned record, not in inference memory or files

#### Scenario: Cross-user access refused
- **WHEN** an authenticated user references a conversation record owned by a different user
- **THEN** Frappe refuses before any history is read, forwarded, or modified

#### Scenario: Privileged role refused on another's thread
- **WHEN** a caller holding a privileged Frappe role references a conversation owned by a different user
- **THEN** the NexMate API refuses exactly as for any other non-owner

#### Scenario: Cross-site access refused
- **WHEN** a request names a conversation whose site differs from the current authoritative site
- **THEN** Frappe refuses even when the user identity matches

### Requirement: Bounded turn history
Each conversation SHALL hold an ordered, bounded turn history (user/assistant roles only). Frappe SHALL enforce a maximum turn count and a maximum total character budget, keeping the most recent turns and discarding older ones first. Only history within budget SHALL cross into inference context. Concurrent appends to one conversation SHALL be serialized (document lock or revision-guarded update); conflicting mutations SHALL fail loudly for retry and SHALL NOT silently overwrite persisted turns.

#### Scenario: Budget enforced
- **WHEN** a conversation exceeds the turn or character budget
- **THEN** older turns are dropped first and inference receives only the bounded tail

#### Scenario: Roles restricted
- **WHEN** history is written or read
- **THEN** every turn carries exactly `user` or `assistant`, and any other role is rejected

#### Scenario: Concurrent mutation serialized
- **WHEN** two mutations target one conversation concurrently
- **THEN** one succeeds and the other fails loudly for retry, with no persisted turn silently overwritten or lost

### Requirement: Owner-checked lifecycle methods
Frappe SHALL expose non-guest, CSRF-protected conversation methods alongside `ask()`: start a conversation, continue one by identifier, fetch its bounded transcript (for UI restore), and reset it (server-side deletion of the owned thread). Every method SHALL verify the caller owns the record on the current site; Guests SHALL be refused; failures SHALL be bounded and sanitized. `ask()` without a conversation identifier SHALL behave as a stateless single turn with no persistence.

#### Scenario: Stateless ask without identifier
- **WHEN** an authenticated user calls `ask()` with no conversation identifier
- **THEN** exactly one turn is answered with no record created or modified

#### Scenario: Owned reset deletes the thread
- **WHEN** the owner resets their conversation
- **THEN** the record and its turns are deleted server-side and later references to it are refused

#### Scenario: Transcript restore is owner-bound
- **WHEN** the owner fetches their conversation transcript
- **THEN** they receive the bounded turn history and nothing from other users' threads

### Requirement: Ownership-stateless inference
Frappe is authoritative for authenticated user identity, current site, and conversation ownership; inference SHALL NOT independently authorize ownership. Inference SHALL treat gateway history as untrusted-until-validated input and MAY validate envelope consistency only: identifier present and well-formed, conversation owner equal to the envelope user, conversation site equal to the trusted site, turns within budget with allowed roles, and authenticated service/gateway provenance. It SHALL use the supplied turns only for the current response, and SHALL persist nothing per-conversation (no files, no cross-request memory keyed by conversation). Legacy caller-owned session semantics SHALL NOT be honored.

#### Scenario: Valid owned history used ephemerally
- **WHEN** a gateway request carries a consistent, in-budget owned conversation from the authenticated service caller
- **THEN** inference answers from those turns and retains no per-conversation state afterwards

#### Scenario: Forged conversation binding refused
- **WHEN** the conversation owner differs from the envelope user or its site differs from the trusted site
- **THEN** inference refuses before history access, routing, retrieval, or execution

### Requirement: Legacy JSON retirement and migration
The file-based session store SHALL be removed: no new JSON session files SHALL be created or read, the store module and its legacy reset endpoint SHALL be deleted, and direct legacy `session_id` continuity SHALL end with explicit refusal (unknown/removed operation), never silent stateless answers. Pre-existing JSON files SHALL be left untouched on disk and never read again. NexMate SHALL NOT reassign or fabricate ownership for legacy sessions; they are retired precisely because ownership cannot be established. Standalone preview/development without Frappe SHALL be stateless (no persistence claim). Operator documentation SHALL describe the cutover: old threads end, new owned threads begin, stale files may be deleted by hand.

#### Scenario: Legacy files ignored
- **WHEN** old JSON session files exist on the inference host
- **THEN** no request reads them and no new files appear beside them

#### Scenario: Legacy session identifier fails explicitly
- **WHEN** a caller supplies a legacy `session_id` expecting continuity
- **THEN** the request is refused explicitly as unknown/removed rather than answered without history

#### Scenario: Legacy reset endpoint gone
- **WHEN** a caller targets the retired session-reset path
- **THEN** it is refused as an unknown/removed operation, never as a successful reset
