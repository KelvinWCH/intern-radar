# Contributing

Issues and pull requests are welcome.

- Run `python scripts/check.py` before opening a PR. It runs the same checks as CI.
- Python is type checked with pyright in strict mode and the frontend uses strict TypeScript, so
  please keep the types honest instead of adding ignores.
- New scrapers should only use public sources: a public list, a public job board API, or a
  posting page. No logins, no getting around bot checks, and keep the request pacing.
- Tests must run offline. Use mock transports instead of real requests and never add paid AI
  calls to the test suite.
- Keep comments short and only where the code isn't obvious.
