# Security Policy

## Supported versions

Only the latest release is supported with security updates.

## Reporting a vulnerability

Please report vulnerabilities privately via
[GitHub Security Advisories](https://github.com/michael-borck/bowerbird/security/advisories/new).
Do not open a public issue for security problems.

You can expect an acknowledgement within a week.

## Security posture worth knowing about

- **BYO API keys are never persisted server-side.** They live in browser
  storage, are passed per request, and are held in memory only for the life
  of the call. If you find a code path that violates this, that is a
  vulnerability — please report it.
- **Server-side fetching of user-supplied URLs is an SSRF surface.** The
  hosted tier restricts what is fetched and does not render arbitrary pages
  in a browser; full screenshots are a self-host/desktop tier feature for
  this reason.
- The hosted free tier enforces concurrency limits via a job queue to keep
  one user from monopolising the box.
