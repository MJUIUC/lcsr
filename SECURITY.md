# Security

## Reporting

Report privately through
[GitHub Security Advisories](https://github.com/Swapnil-jain/lcsr/security/advisories/new).
Private vulnerability reporting is enabled on this repository. Please do not open
a public issue for a vulnerability.

## What this project is, and what it is not

Knowing the threat model saves everyone time, because two things that look like
findings are deliberate.

**`lcsr serve` has no authentication, by design.** It binds to loopback only and
is a single-user tool running on your own machine. Anyone who can reach that
port can already run code as you. It is not built to be exposed to a network,
and putting it behind a public address is out of scope.

Cross-origin writes are still refused, because a page you happen to visit while
the server is running can otherwise POST to a predictable localhost port.

**The deployed site holds no server-side state.** Your log lives in your own
browser's `localStorage` and is posted with each request so the server can
compute what is due. Nothing is retained between requests, and there is no
database, no account and no session. One visitor cannot reach another's data
because the server never holds it.

The consequence worth stating: clearing site data deletes your progress. Use
**Settings → Export** to keep a copy.

## Scope

In scope:

- anything that lets one visitor of the deployed site read or affect another's data
- code execution, path traversal or arbitrary file read through any route
- stored or reflected XSS reachable from data a user can realistically encounter
- a cross-site request that mutates the local server's log

Out of scope:

- the absence of authentication on `lcsr serve` (see above)
- attacks that require already controlling the user's machine or browser
- denial of service against your own local server
- missing hardening headers on a page that serves no third-party content
