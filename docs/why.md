# Why this exists

Pain signals that triggered `bubble-mirror` (collected 2026-10-14):

## Direct quotes (first-person, with cost)

- **forum.bubble.io/t/401306/55** — `rad.dlugowski` (2026-10-08):

  > "This update just made my website too expensive to keep running, so I'll be
  > canceling my subscription and — ironically — rebuilding my website via AI.
  > $7/mo is too expensive so you're gonna spend $20-$200/mo (or more) in
  > subscriptions/tokens to 'save money?'"

  Independent corroborator: `randomanon` calls it a LARP — but does not deny
  the cancellation intent. This is a first-person customer saying they will
  leave the platform over a small price increase.

- **forum.bubble.io/t/400439/5** — `fede.bubble` (Bubble staff, 2026-09-14):

  > "I think what deserves nuance is the why. ... [Bubble's] agency listed
  > project budget starts at $5k per project, and we are talking about the
  > agency account being too expensive for $1k a year. I think it's easy to
  > see why people might prefer to pay $25/mo for Claude and try to figure
  > it out on their own."

  This is **the platform's own employee** describing the same pain from the
  other side: agencies are leaving, leads have plummeted since June 2026,
  and AI is taking the build work.

- **forum.bubble.io/t/401358** — independent community thread titled
  "Bubble's new Starter plan pricing risks developing economies" (2026-10-07).
  Agency owners complaining that the new $39/month base plus per-app
  workload costs kills their model.

## Verified pricing

Source: [bubble.io/blog/agent-2](https://bubble.io/blog/agent-2/) (Bubble's
own announcement, dated 2026-10-06):

| Plan | Before Oct 20, 2026 | After Oct 20, 2026 | Δ |
|---|---|---|---|
| Web-only Starter, monthly | $32/mo | **$39/mo** | +22% |
| Web-only Starter, annual  | $29/mo | **$32/mo** | +10% |
| All other plans | unchanged | unchanged | — |

AI credits now also required for Agent 2 usage. Bubble describes the change as
"aligning pricing with usage." Forum reaction has been uniformly hostile in
the threads cited above.

## Who feels this and what it costs them today

**Who:**
- Solo founders running a marketing/landing site on a Bubble app, paying
  $29-39/mo for what is essentially a static brochure with a custom domain.
  That is `rad.dlugowski` in the first quote.
- Small agencies in developing economies that build Bubble apps for local
  clients and now find the per-app workload cost + base subscription
  wipes out their margin. That is the t/401358 thread.
- Indie hackers who already have a Bubble app and want to move on but
  cannot because Bubble exports only the data and JSON, not a runnable
  site.

**What it costs them today:**
- $29-39/mo per app to keep a brochure on a custom domain.
- For an agency with N client apps, **N × $39 + workload** before they earn
  a cent. (See t/401358 and t/400439.)
- Switching to a real static host (GitHub Pages, Netlify free, Cloudflare
  Pages) costs $0-0/mo for the same brochure, but requires either
  rebuilding by hand or paying SitedIn's closed-source per-page licence.

**What they already pay for a fix:**
- SitedIn's [Bubble Code Export](https://sitedin.io/tools/bubble-code-export)
  starts free for one page, then charges a per-page licence for the full
  crawl. There is no open, scriptable alternative.

## The smallest fix

A 200-line Python script. Paste a public Bubble URL, get a flat folder of
HTML/CSS/JS you can `git push` to GitHub Pages. No Bubble account needed.
No monthly fee. No licence. Apache-2.0.

That is `bubble-mirror`.

## What this is NOT

- Not a Bubble-app port. Backend logic, database, workflows, and authenticated
  state stay on Bubble. The output is a visual snapshot, the same thing
  SitedIn sells.
- Not a replacement for keeping an app running. If the app is genuinely
  interactive (a marketplace, a dashboard, a login), a static mirror is
  the wrong tool — the answer there is to migrate to a real backend, not
  to mirror the front-end.
- Not a hack. It uses the same public HTML the browser sees. No Bubble API
  tokens, no account required, no ToS grey zone.
