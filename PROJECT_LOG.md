# Project Log

## 2026-09-04 — Project initiated

- Confirmed the City of Longmont Cayenta/Capricorn portal exposes smart-meter
  consumption through an authenticated CSV export.
- Verified the apparent daily CSV actually contains 96 quarter-hour readings
  per date and that their sum matches the exported daily total.
- Identified the two-stage export protocol: obtain a short-lived download key,
  then POST it to the Excel export endpoint.
- Created and tested a dedicated guest account with Smart Meter electricity
  permission. The complete chart and CSV export work; no extra explicit portal
  permission is required.
- Decided to build a public, HACS-compatible, Longmont-specific Home Assistant
  integration with an isolated Cayenta client.
- Wrote the initial specification and architecture design. No implementation
  code exists yet.

## Current state

- The approved implementation plan is committed.
- The CSV normalizer and async portal client are implemented on the
  `initial-implementation` branch.
- Nineteen focused tests pass along with Ruff and strict mypy checks.
- GitHub publication is pending because the local `gh` authentication for the
  intended owner is expired.

## Next step

Implement the Home Assistant long-term statistics adapter using test-driven
development.
