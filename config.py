"""Central configuration for the ERPNext AI Copilot.

All tunables (paths, models, chunking, retrieval k, doc source) live here
or in `.env` — never as magic numbers elsewhere in the codebase.
"""

from pathlib import Path

from dotenv import load_dotenv

# Load .env once, here, so every module reading env vars sees the same
# provider configuration.
load_dotenv()

# --- Paths ---------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
RAW_DOCS_DIR = DATA_DIR / "raw_docs"       # crawled markdown, cached locally
CHROMA_DIR = DATA_DIR / "chroma_db"        # persisted vector store (gitignored)

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
CANDIDATE_MULTIPLIER = 2   # fetch K*M raw hits, then keep best-per-document

# --- Confidence thresholds ------------------------------------------------
# Calibrated against measured distributions on the v3/v4 index / eval probes
# (2026-08-23): dev-question top similarities spanned 0.766–0.848,
# off-domain negatives 0.623–0.719.
# Gating policy (service/main.py): ONLY "high" generates an LLM answer.
# "low" (0.72–0.80) and "no_match" (< 0.72) both refuse deterministically —
# mediocre retrieval (e.g. the "override a controller" miss at 0.766, where
# the model fabricated from keyword overlap) must never reach the generator.
CONFIDENCE_HIGH_MIN_SIMILARITY = 0.80
# Just above the highest measured off-domain negative (0.719): anything
# below this is treated as not-about-the-corpus -> no_match, no LLM call.
CONFIDENCE_LOW_MIN_SIMILARITY = 0.72
