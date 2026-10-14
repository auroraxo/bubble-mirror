# bubble-mirror

Free, no-account, no-install way to download a static mirror of a public Bubble app
so you can host it on GitHub Pages, Netlify, Cloudflare Pages, or any static host.

Bubble just raised the web-only Starter plan from **$29 → $32/month** (annual) and
**$32 → $39/month** (monthly) on **October 20, 2026** ([source](https://bubble.io/blog/agent-2/)).
Forum threads immediately filled with people cancelling because **"$7/mo is too expensive
so I'm gonna spend $20-$200/mo"** — see the pain signals in
[`docs/why.md`](docs/why.md).

SitedIn already sells a "Bubble Code Export" product at this exact gap, but it is
closed-source, requires an account past one page, and only runs on their server.
This project is the open, one-command, "no Bubble account required" version of
the same idea.

## What it does

- Takes a public Bubble URL (staging, custom domain, or `*.bubbleapps.io`).
- Crawls the linked pages on the same domain (configurable depth).
- Downloads the rendered HTML and rewrites asset paths to be relative, so the
  output is a flat folder of files you can drop on any static host.
- Has two render modes:
  - **Static** (default, stdlib only): `urllib` HTTP GET. Works without any
    browser. Best for read-only marketing sites and most landing pages.
  - **Visual** (optional): Playwright. Renders the same pages with a headless
    Chromium and saves the post-JS DOM, so it captures client-side work
    Bubble does. Use this for interactive apps where the static snapshot
    is too empty.
- The output is a **visual snapshot**, not a port — Bubble's backend stays
  on Bubble. This is for cancelling the subscription while keeping the
  marketing site visible, archiving a dead project, or moving a brochure
  to a free static host.

## Install

```bash
git clone https://github.com/auroraxo/bubble-mirror
cd bubble-mirror
pip install -e .
```

For the visual renderer:

```bash
pip install -e .[playwright]
playwright install chromium
```

## Usage

```bash
# Single page, static mode (stdlib only, no install required)
bubble-mirror https://your-app.bubbleapps.io -o ./out

# Full site crawl, 2 levels deep
bubble-mirror https://your-app.bubbleapps.io --depth 2 -o ./out

# Visual mode (captures the post-JS DOM)
bubble-mirror https://your-app.bubbleapps.io --render visual -o ./out
```

Then:

```bash
cd out
python3 -m http.server 8080    # verify locally
git init && git add . && git commit -m "static mirror of <url>"
gh repo create my-static-mirror --public --source=. --push
# enable Pages on the main branch → live in 60s, $0/mo
```

## Why this exists

A first-person statement from the pain feed that triggered this build:

> "This update just made my website too expensive to keep running, so I'll
> be canceling my subscription and — ironically — rebuilding my website via
> AI. $7/mo is too expensive so you're gonna spend..."
> — `rad.dlugowski`, [forum.bubble.io/t/401306/55](https://forum.bubble.io/t/401306/55)

The pain is **already paying $29-39/mo for a website that is mostly static
content under a Bubble subdomain**, and now facing a price hike. SitedIn
already charges for this exact conversion. The open version is a 200-line
script and a free `pip install`.

## Status

- v0.1.0 — first run, static + visual renderers, single-page + crawl.
- Public URL: <https://github.com/auroraxo/bubble-mirror> (created 2026-10-14).
- Demo output: see `examples/`.

## License

Apache-2.0.
