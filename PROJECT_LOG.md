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
- Thirty-four focused tests pass along with Ruff and strict mypy checks.
- Confirmed Home Assistant external long-term statistics are hourly. The design
  now preserves all validated 15-minute readings in an integration-owned source
  archive and publishes four-reading hourly sums to the Energy dashboard.
- Added the versioned source archive and the Home Assistant 2026.9 recorder
  adapter. Re-imports rebuild the complete retained series so utility revisions
  replace the matching hourly rows while the exact source values remain intact.
- Raised the minimum runtime to Home Assistant 2026.9.1 and Python 3.14.2 to
  match the API used and verified the integration against that release.
- Implemented the UI config flow, stable hashed duplicate detection, opaque
  statistic identifiers, daily coordinator, config-entry setup/unload/removal,
  and credential reauthentication.
- Added three health sensors and a deliberately minimal diagnostics payload.
- Added public installation, operation, privacy, and removal documentation; an
  MIT license; issue templates; and pinned CI validation workflows.
- Scanned the working tree and complete Git history for every known private
  identifier from portal exploration. No matches were found.
- GitHub publication is pending because the local `gh` authentication for the
  intended owner is expired.

## Next step

Run the mandatory full functionality and security audit, resolve every finding,
then publish the GitHub repository once command-line authentication is restored.

## 2026-09-07 — Full audit, remediation pass 1

### Documentation

- Compared `README.md`, `SPEC.md`, and implementation behavior. Installation,
  source retention, aggregation, refresh, privacy, and removal descriptions
  match the code. No environment variables or user-facing API endpoints exist.
- Verified all documented URLs and current CI usage against the official Home
  Assistant actions and HACS repositories.

### Functionality and cleanup

- Found that transient retries did not honor the portal's `Retry-After` header
  and network operations relied on the parent session timeout. Added a bounded
  30-second `Retry-After` delay and explicit 30-second request timeouts, with
  regression tests.
- Upgraded the test runner requirement from vulnerable pytest 8.4 to pytest
  9.0.3 or newer.
- Results after fixes: 36 tests passed, strict mypy passed for 12 production
  modules, Ruff passed, byte-compilation passed, JSON/YAML parsing passed, and
  `pip check` reported no broken requirements.
- The only test warning is emitted by Home Assistant's own HTTP module for its
  aiohttp application subclass; this integration neither invokes nor controls
  that deprecated class.

### Security

- Bandit reported zero source-code findings.
- Secret-pattern scans and targeted scans of the working tree and complete Git
  history found no private portal identifiers or credentials.
- The integration manifest has no third-party runtime requirements, so it adds
  zero deployable dependency vulnerabilities.
- `pip-audit` found and the project fixed the pytest test-tool vulnerability.
  It also reports three advisory IDs (duplicated across aliases) in
  `cryptography==48.0.1`, an exact transitive pin of the Home Assistant 2026.9.1
  test/runtime baseline. This integration does not import cryptography or use
  the affected certificate-path or PKCS#7 APIs; the package is supplied and
  controlled by Home Assistant, cannot be overridden by this repository, and
  is explicitly excluded from this repository's dependency gate pending an
  upstream Home Assistant release with a remediated pin.

### Audit status

Remediation was applied, so the required clean functionality/security pass must
be rerun before release. Hassfest and HACS validation remain queued in CI
because their official validators are GitHub Actions rather than local Python
packages.

## 2026-09-07 — Full audit, clean local pass

- Phase 2: 36 tests passed with zero failures; Ruff, strict mypy,
  byte-compilation, metadata parsing, and `pip check` all passed. No TODOs,
  debug statements, dead dependencies, or uncommitted build artifacts were
  found.
- Phase 3: Bandit returned zero findings. Source, working-tree, and Git-history
  secret/private-identifier scans returned zero matches. `pip-audit` returned
  zero unignored advisories; the five ignored records are duplicate aliases of
  the three documented Home Assistant-owned `cryptography` advisories from the
  remediation pass.
- Required post-security Phase 2 rerun: all 36 tests, Ruff, strict mypy, and
  byte-compilation passed again with zero project findings.
- Local functionality and security gates are clean. Official Hassfest and HACS
  results must still pass on the public GitHub repository before the release is
  tagged or described as production-ready.
