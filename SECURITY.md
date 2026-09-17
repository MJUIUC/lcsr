# Security

## Reporting

Report privately through
[GitHub Security Advisories](https://github.com/MJUIUC/lcsr/security/advisories/new).
Private vulnerability reporting is enabled on this repository. Please do not
open a public issue for a vulnerability.

## What this project is, and what it is not

Knowing the threat model saves everyone time.

### Desktop app (`lcsr app`)

The primary interface is a native desktop app built with pywebview. It runs
entirely on your own machine:

- **No network server is started.** The UI communicates directly with Python
  via pywebview's JS bridge. There is no HTTP port to attack.
- **All data lives in `~/.lcsr/`.** The log, settings, preferences, and
  cached problem descriptions never leave your machine.
- **LeetCode descriptions are fetched on demand** via LeetCode's GraphQL
  endpoint (no auth required for problem content). Responses are cached
  locally in `~/.lcsr/problem_cache.json`. No other outbound requests are
  made by the app itself.
- **YouTube search** (`youtube-search-python`) scrapes YouTube's public search
  page to surface solution videos after a stuck attempt. No API key, no
  account, no data sent about you.

### Browser-based server (`lcsr serve`)

The original browser interface is still available. It binds to loopback only
(`127.0.0.1`) and is a single-user tool running on your own machine. Anyone
who can reach that port can already run code as you. It is not built to be
exposed to a network.

Cross-origin writes are refused: a page you happen to visit while the server
is running cannot POST to a predictable localhost port and corrupt your log.

### Deployed hosted build (original fork)

The hosted Vercel build (from the original [Swapnil-jain/lcsr](https://github.com/Swapnil-jain/lcsr))
holds no server-side state. The log lives in the visitor's own browser
`localStorage` and is posted with each request. Nothing is retained between
requests; one visitor cannot reach another's data.

This fork does not maintain a hosted deployment. The above applies only if
you deploy the browser-based server yourself.

## Scope

In scope:

- Code execution, path traversal or arbitrary file read through any route
  in `lcsr serve` or `lcsr app`
- A cross-site request that mutates the local server's log (via `lcsr serve`)
- Stored or reflected XSS reachable from data a user can realistically input
  (notes rendered as Markdown, problem descriptions fetched from LeetCode)
- Anything that leaks user data outside the machine without consent

Out of scope:

- The absence of authentication on `lcsr serve` (intentional, loopback only)
- Attacks that require already controlling the user's machine
- Denial of service against your own local server
- Missing hardening headers on a page that serves no third-party content
- LeetCode's own security posture (we fetch from their public API)

## Notes on Markdown rendering

Attempt notes are rendered as Markdown using
[marked.js](https://marked.js.org) with no custom sanitization beyond what
marked provides by default. Notes are written by the user themselves and
rendered only in their own local app — there is no mechanism to share a note
with another user, so XSS in note rendering affects only the note's author.

If you add a sharing or export-to-web feature in a fork, revisit this and
add DOMPurify or equivalent sanitization before rendering user-supplied
Markdown in any multi-user context.
