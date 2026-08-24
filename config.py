"""Central configuration for the ERPNext AI Copilot.

All tunables (paths, models, chunking, retrieval k, doc source) live here
or in `.env` — never as magic numbers elsewhere in the codebase.
"""

from pathlib import Path
import os

from dotenv import load_dotenv

# Load .env once, here, so every module reading env vars sees the same
# provider configuration.
load_dotenv()

# --- Paths ---------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
RAW_DOCS_DIR = DATA_DIR / "raw_docs"       # crawled markdown, cached locally
CHROMA_DIR = DATA_DIR / "chroma_db"        # persisted vector store (gitignored)

# Phase 2 code tools: the single directory tree every file operation is
# scoped to (SECURITY.md "Project-root scoping"). Configurable so the tool
# can be pointed at a real project checkout; defaults to this repo. One
# project, one root — no per-request roots, no workspace registry
# (ARCHITECTURE.md "Scope: single project for now").
_env_root = os.environ.get("PROJECT_ROOT")
PROJECT_ROOT = Path(_env_root).resolve() if _env_root else ROOT_DIR

# Upper bound for a single read_file response: protects the context window
# and the service from accidentally reading multi-MB artifacts. Reading
# something bigger should be a conscious decision (raise the config), not
# an accident.
MAX_READ_FILE_BYTES = int(os.environ.get("MAX_READ_FILE_BYTES", "1_000_000"))

# --- Tier-1 code search (Phase 2) ------------------------------------------
MAX_SEARCH_RESULTS = int(os.environ.get("MAX_SEARCH_RESULTS", "50"))
MATCH_LINE_MAX_CHARS = 240        # long lines are clipped, never wrapped
SEARCH_HARD_MATCH_CAP = 5000      # stop scanning beyond this many hits

# --- Tier-1 explain (Phase 2) ------------------------------------------------
EXPLAIN_MAX_SEARCH_TERMS = 5      # derived from the problem description
EXPLAIN_MAX_FILES = 4             # files whose excerpts reach the generator
EXPLAIN_MAX_EXCERPT_CHARS = 1600  # per-file excerpt ceiling
EXPLAIN_WINDOW_LINES = 14         # context lines around a hit when excerpting

# --- Tier-2 edit flow (Phase 2) ----------------------------------------------
# Proposals expire: a stale diff applied days later is how mistakes happen.
EDIT_PROPOSAL_TTL_MINUTES = int(os.environ.get("EDIT_PROPOSAL_TTL_MINUTES", "15"))

# --- Doc corpus ----------------------------------------------------------
SITEMAP_URL = "https://docs.frappe.io/sitemap.xml"

# Only ingest these spaces (URL path prefixes after the domain).
DOC_SPACE_PREFIXES = (
    "/erpnext/",
    "/framework/",
)

# Versioned subtrees are skipped for now: Phase 1 has no version-detection,
# and mixing v13/v14/v15 answers into one corpus would blur citations.
# See DECISIONS.md [2026-08-23]; revisit for version-awareness (Phase 5+).
EXCLUDED_PATH_PATTERNS = (
    "/erpnext/v",
    "/framework/v",
)


def is_excluded_doc_path(path: str) -> bool:
    """True if a URL/doc path is inside a versioned doc subtree.

    Matches '/erpnext/v13/...' but NOT '/erpnext/valuation-...' — plain
    substring matching would wrongly exclude every current-version page
    whose slug starts with 'v' (found 2026-08-24 when the loader filter
    deleted chunks for valuation/vat/volunteer pages).
    """
    for pattern in EXCLUDED_PATH_PATTERNS:
        if path.startswith(pattern):
            rest = path[len(pattern):len(pattern) + 1]
            if not rest or not rest.isalpha():
                return True
    return False

CRAWL_WORKERS = 4          # concurrent fetch threads (polite)
CRAWL_DELAY_SECONDS = 0.5  # per-thread pause between requests
CRAWL_TIMEOUT_SECONDS = 30
CRAWL_MAX_RETRIES = 3

# --- Embedding / chunking ------------------------------------------------
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"

CHUNK_SIZE_TOKENS = 400        # target ceiling for oversized sections
CHUNK_OVERLAP_TOKENS = 50      # overlap when re-splitting oversized sections
# A node longer than this many characters (~600 tokens at ~4 chars/token)
# gets re-split. Char-based because it only decides *which* nodes to re-split;
# exact sizing is SentenceSplitter's job (token-based).
RESPLIT_THRESHOLD_CHARS = 2400

# Chunks shorter than this are heading fragments / markdown debris with no
# standalone meaning; indexing them pollutes citations (2.1% of corpus).
MIN_CHUNK_CHARS = 50

COLLECTION_NAME = "erpnext_docs"
SOURCE_TYPE_PUBLIC_DOC = "public_doc"

# --- Retrieval -----------------------------------------------------------
# Manual testing against EVALUATION.md questions (2026-08-23, v3 index):
# k=5 missed relevant pages that sat at ranks 6-7 ("create a custom app",
# "child tables"); k=8 surfaces them. Per-document dedupe below keeps the
# effective context diverse rather than one page's sections filling top-k.
RETRIEVAL_K = 8
CANDIDATE_MULTIPLIER = 2   # fetch K*M raw hits per signal, then fuse + dedupe

# --- Hybrid keyword+vector retrieval ---------------------------------------
# Added 2026-08-24 after the verification run showed pure-vector retrieval
# (a) burying exact-term pages (bench commands for Q12) and (b) gating on a
# noisy chunk's top cosine, refusing questions whose correct page sat in the
# candidate pool at mediocre similarity (Q5/Q6/Q15). Both signals are fused
# with Reciprocal Rank Fusion before best-per-document dedupe.
# See DECISIONS.md [2026-08-24].
RRF_K = 60                 # standard RRF dampener; rank weight = 1/(RRF_K + rank)
BM25_K1 = 1.5              # Okapi term-frequency saturation
BM25_B = 0.75              # Okapi document-length normalization
# Lexical evidence outweighs pure vector rank in fusion: without this,
# vector-similar filler chunks (bm25=0, cos~0.75) crowd exact-term pages out
# of top-k (found 2026-08-24 tuning Q3: hooks.md's override_doctype_class
# section lost its slot to unrelated pages the embedding model merely finds
# topic-adjacent).
FUSION_VECTOR_WEIGHT = 1.0
FUSION_KEYWORD_WEIGHT = 1.5
# A document may take a SECOND top-k slot when another of its chunks carries
# near-equal lexical evidence (bm25 >= this fraction of the page's best).
# Huge multi-section pages (hooks.md: 94 chunks) otherwise lose the exact
# section that answers the question to a sibling that ties lexically but
# ranks better semantically (found 2026-08-24 tuning Q3).
DOC_SECOND_CHUNK_MIN_RELATIVE_BM25 = 0.9

# --- Confidence thresholds ------------------------------------------------
# Calibrated against measured distributions on the v3/v4 index / eval probes
# (2026-08-23): dev-question top similarities spanned 0.766-0.848,
# off-domain negatives 0.623-0.719. Recalibrated 2026-08-24 for hybrid
# retrieval (see progress/CURRENT.md): the keyword term-coverage signal now
# participates in the gate, because cosine alone could not separate
# keyword-overlap negatives (0.74-0.76) from hard positives (0.75-0.80).
# Gating policy (service/main.py + retriever.classify_confidence):
#   no_match - distinctive query terms appear nowhere in the retrieved
#              chunks (coverage veto) OR top similarity < LOW: refuse,
#              empty sources, no LLM call.
#   low      - topically close but below the confident bar: deterministic
#              refusal, nearest sources shown, no LLM call.
#   high     - strong vector similarity, or solid similarity corroborated
#              by exact keyword evidence: generate an answer.
CONFIDENCE_HIGH_MIN_SIMILARITY = 0.80
# Below this even "high" needs keyword corroboration to answer; above the
# old refusal line so mediocre-but-real matches can still be rescued.
CONFIDENCE_RESCUE_MIN_SIMILARITY = 0.74
# Just above the highest measured off-domain negative (0.719): anything
# below this is treated as not-about-the-corpus -> no_match, no LLM call.
CONFIDENCE_LOW_MIN_SIMILARITY = 0.72
# Keyword corroboration required to rescue a sub-HIGH similarity into "high".
CONFIDENCE_RESCUE_MIN_COVERAGE = 0.45
# Coverage veto: if even the best retrieved chunk contains almost none of
# the query's distinctive terms, the match is keyword-overlap noise ->
# no_match regardless of cosine (fixes negatives scoring 0.74+ via generic
# words like "frappe"/"configure").
CONFIDENCE_NO_MATCH_MAX_COVERAGE = 0.05
