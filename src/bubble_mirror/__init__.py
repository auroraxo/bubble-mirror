"""bubble-mirror: public-URL → static folder mirror of a Bubble app.

Free, no-account alternative to SitedIn's closed "Bubble Code Export".

Two render modes:
  - static  (default, stdlib only): plain HTTP GET, rewrite asset paths.
  - visual  (optional Playwright): renders the page first (post-JS DOM),
    which is what you need when Bubble builds the page client-side.

The output is a *visual snapshot*, not a port. Bubble's backend stays on
Bubble; this is for cancelling the subscription while keeping the marketing
site visible, archiving a dead project, or moving a brochure to a free
static host.

Usage:
    bubble-mirror https://your-app.bubbleapps.io -o ./out
    bubble-mirror https://your-app.bubbleapps.io --depth 2 -o ./out
    bubble-mirror https://your-app.bubbleapps.io --render visual -o ./out

Stdlib-only by design; Playwright is imported lazily.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Iterable

__version__ = "0.1.0"

UA = "bubble-mirror/0.1 (+https://github.com/auroraxo/bubble-mirror)"

# Attribute URLs worth localising (page links and assets alike).
ATTR_URL = re.compile(
    r"""\b(src|href|poster|data-src|cite)\s*=\s*(["'])([^"'<>]+)\2""",
    re.IGNORECASE,
)
# CSS url(...) inside <style> blocks, style="..." attributes and .css files.
CSS_URL = re.compile(r"""url\(\s*(?P<q>['"]?)(?P<u>[^'")]+)(?P=q)\s*\)""", re.IGNORECASE)
# srcset="a.png 1x, b.png 2x" — candidates split on commas that are not part
# of a URL (URLs may contain commas, e.g. Cloudflare image transforms).
SRCSET_ATTR = re.compile(r"""\b(srcset|imagesrcset)\s*=\s*(["'])([^"']+)\2""", re.IGNORECASE)

# <link rel="..."> values that point at assets rather than pages.
LINK_ASSET_RELS = {
    "stylesheet", "icon", "shortcut icon", "apple-touch-icon",
    "apple-touch-icon-precomposed", "mask-icon", "manifest", "preload",
    "prefetch", "modulepreload",
}
# URL path suffixes we never crawl as pages (they are files).
FILE_SUFFIXES = {
    ".css", ".js", ".mjs", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
    ".ico", ".woff", ".woff2", ".ttf", ".eot", ".otf", ".mp4", ".webm",
    ".mp3", ".wav", ".pdf", ".zip", ".gz", ".json", ".xml", ".txt", ".map",
    ".csv", ".wasm", ".avif", ".bmp", ".tiff",
}
MAX_ASSET_BYTES = 25 * 1024 * 1024
MAX_PAGES_DEFAULT = 30


# --------------------------------------------------------------------------
# URL / path helpers
# --------------------------------------------------------------------------

def _norm(url: str) -> str:
    """Normalise a URL for visited-set keys: drop fragment, keep query."""
    p = urllib.parse.urlparse(url)
    return urllib.parse.urlunparse((p.scheme, p.netloc, p.path or "/", p.params, p.query, ""))


def _same_origin(a: str, b: str) -> bool:
    pa, pb = urllib.parse.urlparse(a), urllib.parse.urlparse(b)
    return pa.scheme in ("http", "https") and (pa.scheme, pa.netloc) == (pb.scheme, pb.netloc)


def _sanitize(raw: str) -> str:
    raw = urllib.parse.unquote(raw)
    return re.sub(r"[^A-Za-z0-9._/-]", "_", raw).strip("/") or "index"


def _local_path(url: str, out: Path, is_page: bool) -> Path:
    """Map a URL to a file path under ``out``.

    Pages:      https://host/        → out/host/index.html
                https://host/about   → out/host/about.html
                https://host/about/  → out/host/about/index.html
    Assets:     always netloc + path (+ query hash when present).
    """
    p = urllib.parse.urlparse(url)
    raw = p.netloc + p.path
    if is_page:
        if p.path in ("", "/"):
            raw = p.netloc + "/index.html"
        elif p.path.endswith("/"):
            raw = p.path and (p.netloc + p.path + "index.html")
        else:
            last = p.path.rsplit("/", 1)[-1]
            if "." not in last:
                raw = p.netloc + p.path + ".html"
        if p.query:
            raw += "_" + hashlib.sha1(p.query.encode()).hexdigest()[:8] + ".html"
    else:
        if p.query:
            raw += "__q_" + hashlib.sha1(p.query.encode()).hexdigest()[:8]
    rel = _sanitize(raw)
    if is_page and not rel.endswith(".html"):
        rel += ".html"
    return out / rel


# --------------------------------------------------------------------------
# Fetch
# --------------------------------------------------------------------------

def _fetch(url: str, timeout: int = 30) -> tuple[bytes, str]:
    """Return (body, content_type). Raises on HTTP errors."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read(MAX_ASSET_BYTES + 1)
        if len(body) > MAX_ASSET_BYTES:
            raise ValueError("asset too large")
        ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        return body, ctype


# --------------------------------------------------------------------------
# HTML parsing
# --------------------------------------------------------------------------

class _PageAssets(HTMLParser):
    """Collect page links, asset URLs, srcsets, and inline CSS from HTML."""

    def __init__(self, page_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.page_url = page_url
        self.page_links: set[str] = set()   # same-origin, crawl candidates
        self.assets: set[str] = set()       # any origin, downloadable
        self.style_blocks: list[str] = []
        self._in_style = False
        self._style_buf: list[str] = []

    def _abs(self, raw: str) -> str | None:
        raw = raw.strip()
        if not raw or raw.startswith(("#", "data:", "javascript:", "mailto:", "tel:", "about:", "blob:")):
            return None
        return urllib.parse.urljoin(self.page_url, raw)

    def _add_asset(self, raw: str | None) -> None:
        if raw:
            self.assets.add(raw)

    def handle_starttag(self, tag: str, attrs) -> None:
        d = {k.lower(): v for k, v in attrs if k}
        if tag == "a":
            u = self._abs(d.get("href", ""))
            if u and _same_origin(u, self.page_url):
                self.page_links.add(u)
            return
        if tag == "link":
            rel = (d.get("rel") or "").lower().strip()
            href = self._abs(d.get("href", ""))
            if href and rel in LINK_ASSET_RELS:
                self._add_asset(href)
            return
        # Everything else with a URL attribute is treated as an asset.
        for k in ("src", "poster", "data-src", "cite"):
            if d.get(k):
                u = self._abs(d[k])
                if u:
                    # Same-origin extensionless URLs are page links (iframes
                    # mostly); cross-origin ones stay embedded as assets.
                    if tag == "iframe" and _same_origin(u, self.page_url):
                        self.page_links.add(u)
                    else:
                        self.assets.add(u)
        if d.get("srcset"):
            self._add_srcset(d["srcset"])
        if d.get("style"):
            self.style_blocks.append(d["style"])
        if tag == "style":
            self._in_style = True

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag == "style" and self._in_style:
            text = "".join(self._style_buf)
            self.assets.update(_css_urls(text, self.page_url))
            self._style_buf = []
            self._in_style = False

    def handle_data(self, data) -> None:
        if self._in_style:
            self._style_buf.append(data)

    def _add_srcset(self, value: str) -> None:
        for candidate in value.split(","):
            token = candidate.strip().split()
            if token:
                u = self._abs(token[0])
                if u:
                    self.assets.add(u)


def _css_urls(css_text: str, base_url: str) -> set[str]:
    out: set[str] = set()
    for m in CSS_URL.finditer(css_text):
        u = m.group("u").strip()
        if u.startswith("data:"):
            continue
        out.add(urllib.parse.urljoin(base_url, u))
    return out


# --------------------------------------------------------------------------
# Rewriting
# --------------------------------------------------------------------------

def _rel(target: Path, start_dir: Path) -> str:
    try:
        return os.path.relpath(target, start_dir).replace(os.sep, "/")
    except ValueError:  # different drive on Windows
        return target.as_posix()


def _rewrite_html(
    text: str,
    page_url: str,
    page_file: Path,
    page_map: dict[str, Path],
    asset_map: dict[str, Path],
) -> str:
    """Rewrite URLs in a page: crawled pages and downloaded assets become
    relative file paths; everything else is left absolute (and still works
    while the original is online)."""

    def resolve(raw: str) -> str | None:
        u = urllib.parse.urljoin(page_url, raw)
        frag = ""
        if "#" in u:
            u, frag = u.split("#", 1)
            frag = "#" + frag
        target = asset_map.get(_norm(u)) or page_map.get(_norm(u))
        if target is None:
            return None
        return _rel(target, page_file.parent) + frag

    def attr_repl(m: re.Match) -> str:
        attr, quote, raw = m.group(1), m.group(2), m.group(3)
        r = resolve(raw)
        if r is None:
            return m.group(0)
        return f"{attr}={quote}{r}{quote}"

    def css_repl(m: re.Match) -> str:
        r = resolve(m.group("u").strip())
        if r is None:
            return m.group(0)
        return f"url({r})"

    def srcset_repl(m: re.Match) -> str:
        attr, quote, value = m.group(1), m.group(2), m.group(3)
        parts: list[str] = []
        for candidate in value.split(","):
            token = candidate.strip().split()
            if not token:
                continue
            r = resolve(token[0])
            rest = " ".join(token[1:])
            parts.append(f"{r if r else token[0]} {rest}".strip())
        return f"{attr}={quote}{', '.join(parts)}{quote}"

    text = SRCSET_ATTR.sub(srcset_repl, text)
    text = ATTR_URL.sub(attr_repl, text)
    text = CSS_URL.sub(css_repl, text)
    return text


def _rewrite_css(css_text: str, css_url: str, css_file: Path, asset_map: dict[str, Path]) -> str:
    def repl(m: re.Match) -> str:
        u = m.group("u").strip()
        if u.startswith("data:"):
            return m.group(0)
        absu = _norm(urllib.parse.urljoin(css_url, u))
        target = asset_map.get(absu)
        if target is None:
            return m.group(0)
        return f"url({_rel(target, css_file.parent)})"

    return CSS_URL.sub(repl, css_text)


# --------------------------------------------------------------------------
# Core mirror pipeline (shared by both render modes)
# --------------------------------------------------------------------------

def _run_mirror(
    start_url: str,
    out: Path,
    fetch_html: Callable[[str], str],
    depth: int,
    verbose: bool,
    max_pages: int,
) -> dict:
    """Crawl pages, download assets, rewrite, write. Returns a summary."""
    out.mkdir(parents=True, exist_ok=True)
    start = _norm(start_url)
    queue: deque[tuple[str, int]] = deque([(start, 0)])
    seen: set[str] = {start}
    page_texts: dict[str, str] = {}
    asset_map: dict[str, Path] = {}
    asset_fail = 0

    # Phase A — crawl pages.
    while queue and len(page_texts) < max_pages:
        url, d = queue.popleft()
        if verbose:
            print(f"[mirror] page {url} (depth {d})", file=sys.stderr)
        try:
            html_text = fetch_html(url)
        except Exception as exc:
            if verbose:
                print(f"          skipped: {exc.__class__.__name__}: {exc}", file=sys.stderr)
            continue
        page_texts[url] = html_text
        if d >= depth:
            continue
        parser = _PageAssets(url)
        try:
            parser.feed(html_text)
        except Exception:
            pass
        for link in sorted(parser.page_links):
            n = _norm(link)
            path = urllib.parse.urlparse(n).path.lower()
            if any(path.endswith(s) for s in FILE_SUFFIXES):
                continue
            if n not in seen and len(seen) < max_pages * 10:
                seen.add(n)
                queue.append((n, d + 1))
        time.sleep(0.15)

    # Phase B — collect + download every asset referenced by any page.
    css_files: dict[str, tuple[Path, str]] = {}  # norm-url -> (local path, url)
    for url, html_text in page_texts.items():
        parser = _PageAssets(url)
        try:
            parser.feed(html_text)
        except Exception:
            pass
        wanted = set(parser.assets)
        for block in parser.style_blocks:
            wanted |= _css_urls(block, url)
        for u in sorted(wanted):
            n = _norm(u)
            if n in asset_map:
                continue
            try:
                body, ctype = _fetch(u)
            except (urllib.error.HTTPError, urllib.error.URLError, ValueError, OSError) as exc:
                asset_fail += 1
                if verbose:
                    print(f"[mirror] asset failed {u} ({exc.__class__.__name__})", file=sys.stderr)
                continue
            target = _local_path(u, out, is_page=False)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
            asset_map[n] = target
            if ctype == "text/css" or target.suffix == ".css":
                try:
                    css_files[n] = (target, body.decode("utf-8", errors="replace"))
                except Exception:
                    pass

    # Phase C — rewrite CSS files (fonts/images referenced from CSS).
    for norm_url, (css_path, css_text) in list(css_files.items()):
        needed = _css_urls(css_text, norm_url)
        for u in sorted(needed):
            n = _norm(u)
            if n in asset_map:
                continue
            try:
                body, _ = _fetch(u)
            except Exception as exc:
                asset_fail += 1
                if verbose:
                    print(f"[mirror] css asset failed {u} ({exc.__class__.__name__})", file=sys.stderr)
                continue
            target = _local_path(u, out, is_page=False)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
            asset_map[n] = target
        new_css = _rewrite_css(css_text, norm_url, css_path, asset_map)
        css_path.write_text(new_css, encoding="utf-8")

    # Phase D — rewrite pages and write them.
    page_map = {u: _local_path(u, out, is_page=True) for u in page_texts}
    for url, html_text in page_texts.items():
        page_file = page_map[url]
        page_file.parent.mkdir(parents=True, exist_ok=True)
        rewritten = _rewrite_html(html_text, url, page_file, page_map, asset_map)
        page_file.write_text(rewritten, encoding="utf-8")

    return {
        "pages": len(page_texts),
        "assets": len(asset_map),
        "asset_failures": asset_fail,
        "out": str(out),
    }


# --------------------------------------------------------------------------
# Render modes
# --------------------------------------------------------------------------

def mirror_static(
    start_url: str,
    out: Path,
    depth: int = 0,
    verbose: bool = True,
    max_pages: int = MAX_PAGES_DEFAULT,
) -> dict:
    """Stdlib-only mirror: plain HTTP GET per page (no JS execution).

    Best for server-rendered pages. If a Bubble app renders its content
    client-side, the result will be an empty shell — use --render visual.
    """

    def fetch_html(url: str) -> str:
        body, ctype = _fetch(url)
        if ctype and "html" not in ctype and ctype != "text/plain":
            raise ValueError(f"not html ({ctype})")
        return body.decode("utf-8", errors="replace")

    summary = _run_mirror(start_url, out, fetch_html, depth, verbose, max_pages)
    summary["render"] = "static"
    return summary


async def _visual_once(urls: list[str]) -> dict[str, str]:
    """Render each URL with headless Chromium; return {url: html}."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise SystemExit(
            "Playwright not installed. Run:\n"
            "  pip install 'bubble-mirror[playwright]' && playwright install chromium"
        )
    results: dict[str, str] = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--no-sandbox"])
        ctx = await browser.new_context(user_agent=UA)
        page = await ctx.new_page()
        for url in urls:
            try:
                await page.goto(url, wait_until="load", timeout=45000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass  # busy pages never go networkidle; 'load' is enough
                results[url] = await page.content()
            except Exception as exc:
                print(f"[visual] {url} failed: {exc.__class__.__name__}", file=sys.stderr)
        await browser.close()
    return results


def mirror_visual(
    start_url: str,
    out: Path,
    depth: int = 0,
    verbose: bool = True,
    max_pages: int = MAX_PAGES_DEFAULT,
) -> dict:
    """Playwright-backed mirror: executes page JS before saving the DOM."""
    # Phase A uses Playwright; asset download/rewrite reuses _run_mirror
    # with a renderer-backed fetch_html via asyncio.run per batch.
    rendered: dict[str, str] = {}

    def fetch_html(url: str) -> str:
        if url in rendered:
            return rendered[url]
        # Render this URL (and any not-yet-rendered queue siblings later).
        batch = asyncio.run(_visual_once([url]))
        rendered.update(batch)
        if url not in rendered:
            raise RuntimeError("render failed")
        return rendered[url]

    summary = _run_mirror(start_url, out, fetch_html, depth, verbose, max_pages)
    summary["render"] = "visual"
    return summary


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="bubble-mirror",
        description="Static-mirror a public Bubble app — no account, no licence.",
    )
    ap.add_argument("url", help="Public Bubble URL (staging, custom domain, or *.bubbleapps.io)")
    ap.add_argument("-o", "--out", default="./out", help="Output directory (default: ./out)")
    ap.add_argument("--depth", type=int, default=0,
                    help="Crawl depth for same-origin links (default: 0 = single page)")
    ap.add_argument("--max-pages", type=int, default=MAX_PAGES_DEFAULT,
                    help=f"Hard cap on crawled pages (default: {MAX_PAGES_DEFAULT})")
    ap.add_argument("--render", choices=("static", "visual"), default="static",
                    help="static = plain HTTP (default, no dependencies); "
                         "visual = run page JS first (needs Playwright)")
    ap.add_argument("--quiet", action="store_true", help="Only print the summary")
    args = ap.parse_args(list(argv) if argv is not None else None)

    out = Path(args.out).resolve()
    try:
        if args.render == "static":
            summary = mirror_static(args.url, out, depth=args.depth,
                                    verbose=not args.quiet, max_pages=args.max_pages)
        else:
            summary = mirror_visual(args.url, out, depth=args.depth,
                                    verbose=not args.quiet, max_pages=args.max_pages)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130

    print(
        f"done: {summary['pages']} page(s), {summary['assets']} asset(s), "
        f"{summary['asset_failures']} failed download(s) → {summary['out']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
