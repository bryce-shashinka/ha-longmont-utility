# Longmont Utility Home Assistant Integration Design

## Decision summary

Build a public, Longmont-specific Home Assistant custom integration with a
separately testable Cayenta portal client. Distribute it as a HACS custom
repository. Version 1 imports electric consumption only and deliberately does
not claim compatibility with other Cayenta utilities.

## Architecture

The integration is divided into four isolated units:

1. **Portal client** — owns authentication, session state, account/meter
   discovery, date-range selection, export-key retrieval, and CSV download.
2. **CSV normalizer** — validates the malformed export and emits timezone-aware
   quarter-hour interval records.
3. **Statistics importer** — converts interval energy into Home Assistant
   cumulative long-term statistics and performs idempotent recent corrections.
4. **Coordinator and config flow** — manages credentials, daily scheduling,
   retries, reauthentication, diagnostics, and setup UI.

Only typed domain objects cross these boundaries. Portal HTML and CSV details
do not leak into the Home Assistant-facing layer.

## Data flow

During setup, the config flow authenticates, discovers authorized electric
meters, and stores the selected meter's opaque identifier with the credentials.
The first coordinator refresh requests up to 90 days. Later refreshes request
the most recent seven complete dates. The parser validates every row and emits
interval records; the importer updates only the integration-owned statistic.

The portal's export is a two-stage authenticated operation: request a
short-lived encrypted key, then POST to `ExcelExport` with that key. The key is
never persisted. Because the selected date range and meter are server-side
session state, one session cannot run concurrent exports.

## Time model

Portal dates use Longmont local time (`America/Denver`). An ordinary row has 96
quarter-hour intervals. DST transition handling is explicit and tested. The
implementation will reject a date whose interval count cannot be mapped
unambiguously rather than invent timestamps.

## Failure behavior

Authentication errors initiate reauthentication. Network and server failures
retain the previous data and use bounded retries. Invalid rows are isolated so
valid days can still import, but validation failures remain visible through
redacted diagnostics. The integration never deletes established statistics
merely because the portal omits a recent day.

## Public-repository safety

All fixtures are synthetic. Repository history must never receive the captured
CSV, account number, meter ID, address, account balance, session cookies,
credentials, CSRF tokens, or export keys. Structured redaction tests cover
exceptions, logs, and diagnostics.

## Verification

Unit tests cover portal response parsing, CSV normalization, decimal totals,
timezone mapping, DST behavior, error classification, and redaction. Mocked
integration tests cover config flow, initial import, repeat updates,
corrections, retries, and reauthentication. CI additionally runs Ruff, mypy,
Hassfest, and HACS validation.

The canonical detailed requirements and acceptance criteria live in
`SPEC.md`.

