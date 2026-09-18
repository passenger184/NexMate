# index-lifecycle Specification

## Purpose

Index state advances through explicit versioned generations with atomic publication, rollback, and coupled lexical/vector state, so rebuilds never destroy unrelated corpora or mix incompatible embeddings.

## Requirements

### Requirement: Versioned index generations with provenance
Every published index state SHALL be an explicit generation recording its identifier, source revisions, embedding model/revision/dimensions/metric, and ACL metadata schema version. Retrieval results SHALL be traceable to their generation.

#### Scenario: Generation identity present
- **WHEN** content is retrieved or a rebuild completes
- **THEN** the active generation and its provenance record are observable without exposing secrets

### Requirement: Atomic publication and rollback
New generations SHALL be built staged and activated by an atomic pointer swap; the prior generation SHALL be retained for rollback. Activation SHALL be all-or-nothing per generation; partial publication SHALL NOT be observable by retrieval.

#### Scenario: Failed build never surfaces
- **WHEN** a staged generation fails validation or the builder crashes
- **THEN** retrieval keeps serving the prior generation unchanged

#### Scenario: Rollback restores service
- **WHEN** an operator rolls back to the prior generation
- **THEN** retrieval serves exactly the prior state, verified by counts and probes

### Requirement: Update and delete semantics
Updates SHALL be applied as new generations (no in-place mutation of the active generation); deletions SHALL remove the content from the staged generation and its lexical snapshot before publication. Deleted content SHALL NOT be retrievable afterwards from any path.

#### Scenario: Deleted document disappears everywhere
- **WHEN** a document is deleted and the new generation publishes
- **THEN** vector, lexical, cache, and citation paths no longer return it

### Requirement: Lexical and vector consistency
The lexical snapshot SHALL be rebuilt from the same staged generation as the vectors before activation, coupling them by construction. A rebuild or mutation SHALL NOT leave lexical state stale relative to vector state; freshness SHALL be verified as part of publication.

#### Scenario: No stale lexical reads
- **WHEN** content is added, changed, or removed and the generation publishes
- **THEN** lexical and vector paths agree on the corpus contents

### Requirement: Unrelated corpora preserved
Rebuilds scoped to one corpus (public, company, code, resolutions) SHALL preserve all other corpora bit-for-bit in the new generation. Destructive full-collection replacement SHALL NOT be used; publication SHALL verify per-corpus counts before activation.

#### Scenario: Public rebuild preserves company data
- **WHEN** a public-only rebuild publishes
- **THEN** company, code, and resolution chunks and counts are unchanged

### Requirement: Embedding compatibility gate
The loader SHALL verify the stored embedding fingerprint (model, revision, dimensions, metric) against the configured model before serving; mismatch SHALL refuse retrieval and require a controlled rebuild/republication. Mixed incompatible vectors in one generation SHALL be prohibited and detected at build time.

#### Scenario: Model change forces controlled rebuild
- **WHEN** the embedding model, revision, dimensions, or metric changes
- **THEN** the old generation refuses to serve and only a rebuilt, re-verified generation activates
