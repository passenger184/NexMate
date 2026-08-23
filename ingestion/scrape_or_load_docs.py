"""Crawl the public ERPNext/Frappe documentation from docs.frappe.io.

Discovers pages via sitemap.xml, filters to the configured doc spaces
(current-version ERPNext manual + Framework docs), fetches each page as
markdown, and caches it under data/raw_docs/ preserving the site's path
structure. Pages already cached are skipped unless --refresh is given.

The git-repo doc source named in PHASE_1_SPEC.md no longer exists (docs
migrated to docs.frappe.io ~2021, see DECISIONS.md) — this crawler is the
spec's own fallback: scraping the live documentation site.

Usage:
    python -m ingestion.scrape_or_load_docs            # full crawl
    python -m ingestion.scrape_or_load_docs --limit 25 # smoke test
    python -m ingestion.scrape_or_load_docs --dry-run  # list URLs only
"""

import argparse
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import requests

import config

SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def _is_doc_url(url: str) -> bool:
    """True if url is a current-version page in one of the ingested spaces."""
    path = urlparse(url).path
    if not any(path.startswith(p) for p in config.DOC_SPACE_PREFIXES):
        return False
    if any(pat in path for pat in config.EXCLUDED_PATH_PATTERNS):
        return False
    return True


def _discover_urls(session: requests.Session) -> list[str]:
    """Fetch and parse sitemap.xml, return filtered doc URLs in stable order."""
    resp = session.get(config.SITEMAP_URL, timeout=config.CRAWL_TIMEOUT_SECONDS)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    urls = [loc.text.strip() for loc in root.findall("sm:url/sm:loc", SITEMAP_NS) if loc.text]
    filtered = sorted(u for u in urls if _is_doc_url(u))
    print(f"Sitemap: {len(urls)} total URLs, {len(filtered)} match doc spaces "
          f"({', '.join(config.DOC_SPACE_PREFIXES)})")
    return filtered


def _url_to_path(url: str) -> Path:
    """Map a docs URL to a local markdown file path under RAW_DOCS_DIR."""
    path = urlparse(url).path.strip("/")
    parts = [p for p in path.split("/") if p]
    return config.RAW_DOCS_DIR.joinpath(*parts).with_suffix(".md")


def _fetch_one(session: requests.Session, url: str) -> tuple[str, str | None]:
    """Fetch one page's markdown via the wiki's official .md alternate.

    Plain GET returns rendered HTML; every page declares
    <link rel="alternate" type="text/markdown"> at {url}.md, which serves
    the raw markdown with YAML front-matter.

    Some sitemap entries are stale aliases that 302-redirect to a new
    canonical page — their {url}.md 404s even though the target page exists.
    On 404 we follow the HTML redirect and retry .md at the canonical URL.
    Returns (url, markdown-or-None); None means permanently failed.
    """
    text = _fetch_md(session, f"{url}.md")
    if text is not None:
        return url, text

    # 404 fallback: resolve where this alias redirects to in its HTML form,
    # then fetch the markdown alternate of the canonical URL.
    try:
        resp = session.get(url, timeout=config.CRAWL_TIMEOUT_SECONDS, allow_redirects=True)
        time.sleep(config.CRAWL_DELAY_SECONDS)
        final_path = urlparse(resp.url).path.rstrip("/")
        # only accept canonical targets still inside the ingested corpus —
        # many old manual aliases now redirect to OTHER Frappe product docs
        # (/hr/, /lending/, ...) hosted on this same domain
        canonical = f"https://docs.frappe.io{final_path}"
        if resp.status_code == 200 and _is_doc_url(canonical) and f"{final_path}.md" != f"{urlparse(url).path.rstrip('/')}.md":
            text = _fetch_md(session, f"{canonical}.md")
            if text is not None:
                # return the canonical URL so the page caches under its
                # real path instead of the stale alias
                return canonical, text
    except requests.RequestException:
        pass
    return url, None


def _fetch_md(session: requests.Session, md_url: str) -> str | None:
    """GET one {url}.md resource; return body or None on permanent failure."""
    for attempt in range(1, config.CRAWL_MAX_RETRIES + 1):
        try:
            resp = session.get(md_url, timeout=config.CRAWL_TIMEOUT_SECONDS)
            if resp.status_code == 404:
                return None  # no markdown alternate here; caller may fall back
            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.HTTPError(f"{resp.status_code} for {md_url}", response=resp)
            resp.raise_for_status()
            time.sleep(config.CRAWL_DELAY_SECONDS)
            return resp.text
        except (requests.RequestException, OSError) as exc:
            wait = 2**attempt
            print(f"  retry {attempt}/{config.CRAWL_MAX_RETRIES} for {md_url} after {wait}s: {exc}",
                  file=sys.stderr)
            if attempt == config.CRAWL_MAX_RETRIES:
                return None
            time.sleep(wait)
    return None  # unreachable; satisfies type checkers


def _looks_like_markdown(text: str) -> bool:
    """Cheap sanity check that the wiki served markdown, not rendered HTML."""
    head = text.lstrip()[:400].lower()
    return text.startswith("---") or "<!doctype html" not in head and "<html" not in head


def crawl(refresh: bool = False, limit: int | None = None, dry_run: bool = False) -> None:
    session = requests.Session()
    session.headers["User-Agent"] = "erpnext-ai-copilot-ingest/0.1 (local dev; CC-BY-SA docs)"

    urls = _discover_urls(session)
    if limit is not None:
        urls = urls[:limit]
        print(f"Limited to first {len(urls)} URLs")

    todo = []
    for url in urls:
        dest = _url_to_path(url)
        if not refresh and dest.is_file():
            continue
        todo.append((url, dest))
    skipped = len(urls) - len(todo)
    if skipped:
        print(f"{skipped} pages already cached, skipping")
    if dry_run:
        for url, _dest in todo:
            print(f"would fetch {url}")
        return

    failures: dict[str, str] = {}
    fetched = 0
    with ThreadPoolExecutor(max_workers=config.CRAWL_WORKERS) as pool:
        futures = {pool.submit(_fetch_one, session, url): (url, dest)
                   for url, dest in todo}
        done = 0
        for future in as_completed(futures):
            original_url, _dest = futures[future]
            fetched_url, text = future.result()
            done += 1
            if text is None:
                failures[original_url] = "unreachable after retries"
                continue
            if not _looks_like_markdown(text):
                failures[original_url] = "response did not look like markdown"
                continue
            # may differ from original_url when a stale alias was resolved
            # to its canonical page — cache under the canonical path
            dest = _url_to_path(fetched_url)
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                dest.write_text(text, encoding="utf-8")
            except OSError as exc:
                failures[url] = f"write failed: {exc}"
                continue
            fetched += 1
            if fetched % 100 == 0:
                print(f"fetched {fetched}/{len(todo)} (done {done}/{len(todo)})")

    print(f"\nCrawl complete: fetched {fetched}, failed {len(failures)}, "
          f"cached-before {skipped}")
    if failures:
        fail_file = config.RAW_DOCS_DIR / "_failed_urls.txt"
        fail_file.parent.mkdir(parents=True, exist_ok=True)
        fail_file.write_text(
            "\n".join(f"{u}\t{r}" for u, r in sorted(failures.items())) + "\n",
            encoding="utf-8",
        )
        print(f"FAILURES recorded in {fail_file}:")
        for u, r in list(sorted(failures.items()))[:20]:
            print(f"  {u} -> {r}")
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--refresh", action="store_true", help="re-fetch even cached pages")
    parser.add_argument("--limit", type=int, default=None,
                        help="only consider the first N discovered URLs")
    parser.add_argument("--dry-run", action="store_true", help="list target URLs, fetch nothing")
    args = parser.parse_args()

    if not args.dry_run:
        config.RAW_DOCS_DIR.mkdir(parents=True, exist_ok=True)
    crawl(refresh=args.refresh, limit=args.limit, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
