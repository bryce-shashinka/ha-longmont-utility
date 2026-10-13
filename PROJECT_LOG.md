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

## 2026-09-09 — GitHub validator remediation

- Created and pushed the public `bryce-shashinka/ha-longmont-utility`
  repository.
- Official run 1 confirmed the Python quality job but found three release
  metadata omissions: Hassfest required the imported `recorder` integration in
  `dependencies`; HACS required a local brand icon and at least one repository
  topic.
- Added the recorder dependency, the US country scope, and an original local
  icon with no municipal seal, text, or official Longmont branding. The icon
  was generated with the built-in image tool from a project-specific prompt
  describing a lightning bolt and four interval bars.
- Added the public repository topics `home-assistant`, `hacs`, `smart-meter`,
  `longmont`, and `energy` through GitHub settings.
- Official run 2 passed the Python quality and Hassfest jobs. Its sole failure
  was HACS's repository-topic check because the run completed before the topics
  were saved; the next pushed commit will validate the corrected repository
  metadata.
- During the clean-pass rerun, `pip-audit` identified PYSEC-2026-3721 in the
  isolated development environment's `pip==26.1.2`. Upgraded that local tool to
  the fixed 26.2 release without changing integration runtime dependencies.
- Repeated the complete security-to-functionality sequence after the upgrade:
  `pip-audit` found zero unignored advisories, Bandit and private-data scans
  found zero issues, and all 36 tests, Ruff, strict mypy, byte-compilation,
  metadata parsing, `pip check`, and diff checks passed.

## 2026-09-09 — Final audit summary

- The final local audit completed a clean documentation, functionality,
  cleanup, and security pass with zero project findings. All 36 tests passed;
  Ruff, strict mypy, byte-compilation, metadata parsing, dependency integrity,
  Bandit, dependency auditing, private-data scans, and diff checks were clean.
- GitHub Actions run 3 passed all official jobs: Python quality, Home Assistant
  Hassfest, and HACS validation. This confirms the repository metadata,
  manifest, local branding, and public topics satisfy the release validators.
- No real portal source file, address, account number, meter identifier, guest
  email, cookie, or credential is present in the working tree or Git history.
  The integration retains exact imported quarter-hour readings locally in Home
  Assistant while generating hourly Energy statistics from that source archive.
- Audit result: zero functionality issues and zero integration-owned security
  issues in one clean pass. The repository is ready for a release tag after
  this final audit record's own CI run passes.

## 2026-09-10 — Live portal TLS remediation

- The first live Home Assistant config-flow attempt returned `cannot_connect`
  even though the restricted guest credentials were verified in the portal UI.
- Reproduced the failure before authentication: the portal serves only its leaf
  certificate and omits its advertised Sectigo Public Server Authentication CA
  DV R36 intermediate, causing standard OpenSSL/aiohttp verification to fail
  with `unable to verify the first certificate`.
- Added that specific public intermediate to the portal client's normal system
  trust context. Hostname and certificate verification remain enabled; the
  integration does not use an insecure verification bypass.
- Added a regression test that verifies every portal request receives a TLS
  context containing the expected intermediate fingerprint. The test failed
  before the fix and passed afterward; the full suite now passes 37 tests along
  with Ruff, strict mypy, byte-compilation, and diff checks.

## 2026-09-10 — Live import remediation

- The restricted guest account authenticated and meter discovery succeeded on
  the installed Home Assistant 2026.9.1 instance. The first refresh then
  exposed three additional differences between the observed browser workflow
  and the live non-browser contract.
- Corrected the daily refresh POST target from the form's stale
  `/app/index.jsp` action to the `/app/capricorn` endpoint selected by the
  portal's own JavaScript.
- Accepted the portal's `application/force-download` response only when its
  content disposition identifies a `.csv` attachment. HTML and other payloads
  remain rejected.
- Confirmed the supplied original CSV and the current live export end with a
  sparse `* Note:` footer after blank lines. The parser now ignores only that
  recognizable non-data row and continues to reject malformed measurement
  rows.
- Changed the Home Assistant statistics handoff from a one-shot generator to a
  list because Home Assistant validates the iterable before placing it on the
  recorder queue. The generator was otherwise exhausted before insertion.
- Added regression coverage for all three behaviors. The suite now passes 39
  tests with Ruff, strict mypy, byte-compilation, and diff checks clean.
- Deployed the changes to the live Home Assistant instance. Verified the entry
  is loaded, three health sensors are available, 6,624 exact quarter-hour
  readings are retained in the private source archive, and 1,656 hourly
  statistics are committed for the same July 2 through September 8 local-time
  coverage.

## 2026-10-12 — Tiered cost estimate (0.2.0)

- Home Assistant's Energy dashboard cannot apply a price entity to an
  external statistic, so the integration now imports a second external
  statistic, `<suffix>_energy_cost`, in US dollars.
- Added `tariff.py` with the dated residential RE schedule (2026 prices:
  $17.50 customer charge; 750/1,500 kWh tiers at 10.57/12.45/16.18¢
  non-summer and 11.64/13.73/17.83¢ summer, franchise fee included). Each
  quarter-hour is priced against cumulative billing-cycle usage, split exactly
  across tier boundaries; the customer charge is spread over the cycle's
  actual hours.
- Added an options flow for the billing-cycle start day (1-28, default 1);
  changing it reloads the entry and recalculates the full retained archive.
