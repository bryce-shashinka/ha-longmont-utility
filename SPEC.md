# Longmont Utility for Home Assistant

## Project overview

`ha-longmont-utility` is a public, HACS-compatible Home Assistant custom
integration that imports City of Longmont smart-meter electricity usage into
Home Assistant's Energy dashboard.

The City portal presents usage as daily or hourly charts, but its daily CSV
contains 96 quarter-hour kWh readings per date plus a daily total. The CSV
header incorrectly describes only 24 hourly fields. This integration will
retrieve that export, normalize it, and write timestamped consumption into
Home Assistant long-term statistics.

## Goals

- Configure the integration through the Home Assistant UI.
- Authenticate with a dedicated Longmont utility guest account.
- Retrieve the latest available quarter-hour consumption automatically.
- Correctly parse the portal's malformed CSV.
- Preserve every validated 15-minute source reading locally at full fidelity.
- Backfill and revise recent statistics without double-counting.
- Expose useful health diagnostics without leaking private account data.
- Be installable as a custom repository through HACS.

## Non-goals

- Real-time load monitoring or automation triggers.
- Billing-grade cost calculation.
- Water, gas, generation, or billed-usage imports in version 1.
- Generic support for every Cayenta-powered utility portal.
- Browser automation, PDF parsing, or chart-image extraction.
- Storing utility credentials outside Home Assistant's config-entry storage.

## Supported environment

- Home Assistant 2026.9.1 or newer and Python 3.14.2 or newer.
- City of Longmont Utility Billing guest accounts with **Smart Meter →
  Electricity** permission.
- One electric meter per config entry in version 1.

## Portal contract

The integration will model these observed portal operations behind a dedicated
client interface:

1. Establish an authenticated Cayenta/Capricorn session.
2. Select the authorized account and electric meter.
3. Load the Smart Meter consumption view and set a daily date range.
4. Submit the date-range refresh to `POST /app/capricorn`; the form's static
   `/app/index.jsp` action is stale and the portal UI rewrites it in JavaScript.
5. Request a short-lived export key:
   `GET /app/capricorn?para=ajaxDownloadConsumptionData&type=smartmeterV3&inquiryType=hydro&isGenerationDataAvailable=false`
6. Retrieve the CSV:
   `POST /app/ExcelExport?key=<short-lived-key>`

The CSV response currently uses the nonstandard `application/force-download`
media type. It is accepted only when `Content-Disposition` marks it as a `.csv`
attachment; normal CSV media types remain accepted.

The server appears to keep the selected meter and date range in session state,
so the client must serialize operations within a session. It must never log
credentials, cookies, export keys, account numbers, meter IDs, addresses, or
raw response bodies.

## CSV interpretation

- Column 1 is the local reading date.
- Columns 2–97 are 96 consecutive 15-minute kWh intervals.
- The next populated field is the daily kWh total.
- Extra trailing empty fields are ignored.
- Blank rows and the portal's single-field `* Note:` footer are ignored.
- Header labels are not used to determine interval count because the observed
  header has only 26 fields and is incorrect.
- A row is accepted only if it contains exactly 96 finite, non-negative
  interval readings and a finite, non-negative total.
- The interval sum must match the daily total within a small documented
  decimal tolerance. A mismatch rejects that row and records a diagnostic.
- Dates are interpreted in `America/Denver`. Daylight-saving transitions must
  be handled explicitly; ambiguous or nonexistent local timestamps must not be
  silently shifted.

## Source archive

Every validated 15-minute reading is retained in Home Assistant's `.storage`
system under an integration-owned, config-entry-specific key. The archive uses
UTC ISO timestamps and decimal kWh strings so values can be reproduced exactly
without binary floating-point loss. New downloads upsert timestamps, allowing
the seven-day refresh window to capture utility revisions without duplicates.

The archive is retained for the lifetime of the config entry. Removing the
config entry removes its archive. The integration does not retain raw CSV,
portal HTML, HTTP headers, cookies, export keys, account numbers, or meter IDs.
Archive data is not exposed through diagnostics.

## Home Assistant data model

The primary output is an external long-term statistic suitable for selection
as grid consumption in the Energy dashboard:

- statistic ID: `longmont_utility:<entry-derived-id>_energy_consumption`
- unit: `kWh`
- device class: energy
- state class semantics: total increasing

Home Assistant long-term external statistics are hourly. Four consecutive
15-minute source readings are summed into one hourly sample, and each hourly
sample contributes to a cumulative sum. Re-importing an existing time range
replaces/corrects the integration-owned statistics rather than appending
duplicates. The full 15-minute readings remain available in the source archive.

Diagnostic entities:

- Last successful update
- Latest utility interval
- Utility data age

Diagnostics must use opaque entry-derived identifiers and redact all private
portal identifiers.

## Configuration and authentication

The config flow requests portal email and password, validates authentication,
discovers authorized electric meters, and creates one entry for the selected
meter. Credentials remain in Home Assistant's config-entry storage and are
never written to logs or diagnostics.

Authentication failure after setup starts Home Assistant's reauthentication
flow. Transient portal failures retain existing statistics and retry with
bounded exponential backoff.

## Update behavior

- Poll once daily after the portal normally publishes the previous day's data.
- Re-fetch the most recent seven complete local dates on every update.
- Initial setup imports up to 90 days, matching the portal's supported daily
  query window.
- Missing newest data is treated as normal latency, not deletion.
- Revised recent readings replace the integration-owned values for those
  timestamps.
- Requests use conservative timeouts, bounded retries, and no concurrent
  operations within the same authenticated session.

## Error handling

- Invalid credentials: abort setup or start reauthentication.
- Portal markup/protocol change: surface `UpdateFailed`, preserve prior data,
  and include only a redacted error category in diagnostics.
- Malformed CSV row: reject the export, retain the previously archived source,
  and expose a redacted validation failure.
- Daily-total mismatch: reject the affected row.
- Partial date range: import the complete validated rows that the portal
  returns; an entirely empty export is rejected.
- Rate limiting or server errors: retry with bounded backoff and respect
  `Retry-After` when present.

## Security and privacy

The public repository must never contain real credentials, cookies, CSRF
tokens, short-lived export keys, account numbers, meter IDs, addresses,
balances, names, captured HTML, browser traces, or the original user CSV.

Tests use generated identifiers and synthetic CSV values. HTTP fixtures are
hand-authored and minimized. Logs and diagnostics are tested for redaction.

## Repository and quality requirements

- Public Git repository named `ha-longmont-utility`.
- HACS-compatible custom integration under
  `custom_components/longmont_utility/`.
- Python formatted and linted with Ruff and type-checked with mypy.
- Tests use pytest and Home Assistant custom-component test conventions.
- GitHub Actions run lint, type checks, unit/integration tests, Hassfest, and
  HACS validation.
- Conventional commit messages.
- README includes installation, guest-account setup, Energy dashboard setup,
  limitations, troubleshooting, privacy, and removal instructions.

## Acceptance criteria

1. A user can install the repository through HACS and add the integration from
   Home Assistant's UI.
2. Valid Longmont guest credentials authenticate; invalid credentials produce
   a clear, non-secret error.
3. The restricted Smart Meter permission is sufficient for discovery and
   export.
4. A synthetic malformed-header CSV is parsed into exactly 96 correctly timed
   intervals per ordinary date.
5. Interval sums are validated against daily totals.
6. Every validated 15-minute reading is upserted into the local source archive
   with exact decimal fidelity and remains available for reprocessing.
7. Initial import backfills up to 90 days and subsequent updates revisit seven
   days without duplicating consumption.
8. Four quarter-hour readings are aggregated into each hourly statistic, and
   imported statistics are selectable as grid consumption in HA's Energy
   dashboard.
9. Credential expiry invokes reauthentication.
10. Tests prove sensitive portal data is absent from logs and diagnostics.
11. All repository tests and public validation workflows pass.
