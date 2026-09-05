# Longmont Utility Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a public HACS-compatible Home Assistant custom integration that imports City of Longmont quarter-hour electric consumption into the Energy dashboard.

**Architecture:** A typed async portal client owns the Cayenta session and export protocol; a pure parser converts the malformed CSV into timezone-aware interval records; an importer writes idempotent cumulative long-term statistics. Home Assistant config flow and coordinator compose those units and expose redacted health diagnostics.

**Tech Stack:** Python 3.13, Home Assistant custom-component APIs, `aiohttp`, `pytest`, `pytest-homeassistant-custom-component`, Ruff, mypy, Hassfest, HACS validation, GitHub Actions.

**Spec:** `SPEC.md` and `docs/superpowers/specs/2026-09-04-longmont-utility-design.md`

## Global Constraints

- Integration domain is `longmont_utility`; repository name is `ha-longmont-utility`.
- Version 1 supports Longmont electricity consumption and one selected electric meter per config entry.
- Ordinary dates contain exactly 96 non-negative finite 15-minute kWh readings; malformed rows are rejected.
- Portal dates use `America/Denver`; DST ambiguity must never be silently shifted.
- Initial import is at most 90 days; recurring refresh revisits seven complete local dates once daily.
- Credentials stay in Home Assistant config-entry storage and all private portal identifiers and payloads are redacted.
- No real portal HTML, CSV, credentials, account IDs, meter IDs, addresses, balances, tokens, or cookies enter the repository.
- Requests within one portal session are serialized and use bounded timeouts and retry behavior.
- Use conventional commits; every task must pass its focused tests before commit.

---

## File map

- `custom_components/longmont_utility/const.py`: domain constants, configuration keys, timing and redaction constants.
- `custom_components/longmont_utility/models.py`: immutable interval and meter domain types.
- `custom_components/longmont_utility/csv_parser.py`: pure malformed-export normalization and validation.
- `custom_components/longmont_utility/client.py`: async Cayenta authentication, discovery, range selection, and two-stage export.
- `custom_components/longmont_utility/statistics.py`: conversion and idempotent HA external-statistics writes.
- `custom_components/longmont_utility/coordinator.py`: refresh orchestration and error mapping.
- `custom_components/longmont_utility/config_flow.py`: setup and reauthentication UI.
- `custom_components/longmont_utility/sensor.py`: three diagnostic entities.
- `custom_components/longmont_utility/__init__.py`: config-entry lifecycle and platform forwarding.
- `tests/`: synthetic fixtures and focused unit/integration tests matching each module.

### Task 1: Repository scaffold and CSV normalizer

**Files:**
- Create: `pyproject.toml`, `requirements_test.txt`, `hacs.json`, `custom_components/longmont_utility/manifest.json`
- Create: `custom_components/longmont_utility/const.py`, `models.py`, `csv_parser.py`
- Create: `tests/conftest.py`, `tests/test_csv_parser.py`, `tests/fixtures/smart_meter.csv`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `IntervalReading(start: datetime, energy_kwh: Decimal)`, `ParsedDay(reading_date: date, intervals: tuple[IntervalReading, ...], total_kwh: Decimal)`, `parse_smart_meter_csv(payload: str, timezone: ZoneInfo) -> tuple[ParsedDay, ...]`, and `CsvValidationError`.

- [x] **Step 1: Write failing parser tests**

Create synthetic CSV data whose header has 24 misleading labels while each row has 96 quarter-hour values and a total. Assert 96 ordered `America/Denver` timestamps, exact Decimal values, total validation, CRLF support, trailing-empty-field tolerance, and rejection of negative, non-finite, wrong-count, duplicate-date, and mismatched-total rows. Include spring-forward and fall-back dates and assert `CsvValidationError` instead of timestamp invention when 96 values cannot represent the local day unambiguously.

- [x] **Step 2: Run the focused tests and confirm failure**

Run: `python -m pytest tests/test_csv_parser.py -q`

Expected: collection fails because `custom_components.longmont_utility.csv_parser` does not exist.

- [x] **Step 3: Implement the typed parser and minimal packaging**

Use `csv.reader`, `Decimal`, and `ZoneInfo`. Ignore header cardinality, require 96 interval fields and one populated total, reject non-finite/negative values, compare `sum(intervals)` to total with `Decimal("0.001")` tolerance, reject duplicate dates, and map ordinary dates from local midnight in 15-minute increments only when timezone round-trips are unambiguous. Define constants:

```python
DOMAIN = "longmont_utility"
PORTAL_TIME_ZONE = "America/Denver"
INTERVALS_PER_ORDINARY_DAY = 96
TOTAL_TOLERANCE_KWH = Decimal("0.001")
```

- [x] **Step 4: Run parser tests and static checks**

Run: `python -m pytest tests/test_csv_parser.py -q && ruff check custom_components tests && mypy custom_components/longmont_utility`

Expected: all commands exit 0.

- [x] **Step 5: Commit**

```bash
git add .gitignore pyproject.toml requirements_test.txt hacs.json custom_components tests
git commit -m "feat: parse Longmont interval exports"
```

### Task 2: Async Cayenta portal client

**Files:**
- Create: `custom_components/longmont_utility/client.py`
- Create: `tests/test_client.py`
- Create: `tests/fixtures/login.html`, `tests/fixtures/account.html`, `tests/fixtures/smart_meter.html`

**Interfaces:**
- Consumes: `ParsedDay`, `parse_smart_meter_csv()`.
- Produces: `MeterInfo(account_ref: str, meter_ref: str, label: str)`, `LongmontPortalClient(session: ClientSession, username: str, password: str)`, `async authenticate() -> None`, `async discover_meters() -> tuple[MeterInfo, ...]`, and `async download_usage(meter: MeterInfo, start: date, end: date) -> tuple[ParsedDay, ...]`.
- Produces exceptions: `InvalidAuth`, `PortalProtocolError`, `PortalUnavailable` with redacted messages.

- [ ] **Step 1: Write failing mocked HTTP tests**

Assert login form discovery and submission, failed-login classification, account/meter discovery, daily range selection, export-key GET, empty POST to `/app/ExcelExport?key=...`, session serialization, 90-day limit enforcement, timeouts, `Retry-After`, and redacted exceptions. Synthetic fixtures use `acct-test-1`, `meter-test-1`, and `person@example.invalid` only.

- [ ] **Step 2: Run client tests and confirm failure**

Run: `python -m pytest tests/test_client.py -q`

Expected: FAIL because `LongmontPortalClient` is undefined.

- [ ] **Step 3: Implement the client**

Use injected `aiohttp.ClientSession`, `asyncio.Lock`, explicit request timeouts, bounded retry for 429/5xx, and HTML form parsing limited to required hidden fields. Keep cookies in the injected session, export keys in local variables, and never include response bodies or identifiers in exception strings. Reject cross-origin form actions and unexpected content types.

- [ ] **Step 4: Run focused and full tests**

Run: `python -m pytest tests/test_client.py tests/test_csv_parser.py -q && ruff check custom_components tests && mypy custom_components/longmont_utility`

Expected: all commands exit 0.

- [ ] **Step 5: Commit**

```bash
git add custom_components/longmont_utility/client.py tests/test_client.py tests/fixtures
git commit -m "feat: add Longmont portal client"
```

### Task 3: Long-term statistics importer

**Files:**
- Create: `custom_components/longmont_utility/statistics.py`
- Create: `tests/test_statistics.py`

**Interfaces:**
- Consumes: `tuple[ParsedDay, ...]`, a config-entry-derived public-safe statistic suffix, and Home Assistant recorder statistics APIs.
- Produces: `async_import_consumption_statistics(hass: HomeAssistant, statistic_id: str, days: tuple[ParsedDay, ...]) -> None` and `build_statistic_samples(days: tuple[ParsedDay, ...]) -> list[StatisticData]`.

- [ ] **Step 1: Write failing statistics tests**

Assert 15-minute samples have cumulative `sum` and interval `state`, stable metadata uses kWh/energy/total-increasing semantics, repeat imports do not add consumption, corrected intervals replace recent integration-owned samples, and statistic IDs contain no account or meter references.

- [ ] **Step 2: Run focused tests and confirm failure**

Run: `python -m pytest tests/test_statistics.py -q`

Expected: FAIL because the statistics module does not exist.

- [ ] **Step 3: Implement conversion and correction-safe import**

Build deterministic cumulative values in timestamp order. Read the prior sample immediately before the replacement range, add new interval energy to that baseline, clear only this integration-owned statistic's overlapping range through the supported recorder API, then call `async_add_external_statistics`. Refuse statistic IDs outside the `longmont_utility:` namespace.

- [ ] **Step 4: Run statistics and parser tests**

Run: `python -m pytest tests/test_statistics.py tests/test_csv_parser.py -q && ruff check custom_components tests && mypy custom_components/longmont_utility`

Expected: all commands exit 0.

- [ ] **Step 5: Commit**

```bash
git add custom_components/longmont_utility/statistics.py tests/test_statistics.py
git commit -m "feat: import Longmont energy statistics"
```

### Task 4: Config flow, coordinator, and reauthentication

**Files:**
- Create: `custom_components/longmont_utility/__init__.py`, `config_flow.py`, `coordinator.py`, `strings.json`, `translations/en.json`
- Create: `tests/test_config_flow.py`, `tests/test_coordinator.py`, `tests/test_init.py`
- Modify: `custom_components/longmont_utility/manifest.json`, `const.py`

**Interfaces:**
- Consumes: `LongmontPortalClient`, `MeterInfo`, `async_import_consumption_statistics()`.
- Produces: `LongmontDataUpdateCoordinator`, config entry data keys `CONF_USERNAME`, `CONF_PASSWORD`, `CONF_ACCOUNT_REF`, `CONF_METER_REF`, and `CONF_STATISTIC_SUFFIX`.

- [ ] **Step 1: Write failing HA lifecycle tests**

Assert user flow validates credentials, offers discovered meters, creates a unique entry, stores no password in title/options/diagnostics, initial refresh requests at most 90 days, recurring refresh requests seven complete local dates, `InvalidAuth` initiates reauth, temporary failures raise `UpdateFailed`, unload succeeds, and one daily listener is registered.

- [ ] **Step 2: Run focused tests and confirm failure**

Run: `python -m pytest tests/test_config_flow.py tests/test_coordinator.py tests/test_init.py -q`

Expected: FAIL because config flow and coordinator modules do not exist.

- [ ] **Step 3: Implement config-entry lifecycle**

Use Home Assistant's shared aiohttp session, `DataUpdateCoordinator`, config-entry runtime data, and standard `SOURCE_REAUTH` flow. Generate `CONF_STATISTIC_SUFFIX` with `uuid4().hex`, never from portal IDs. Calculate date windows in `America/Denver`, excluding the current local date.

- [ ] **Step 4: Run lifecycle and full tests**

Run: `python -m pytest tests -q && ruff check custom_components tests && mypy custom_components/longmont_utility`

Expected: all commands exit 0.

- [ ] **Step 5: Commit**

```bash
git add custom_components/longmont_utility tests
git commit -m "feat: add Longmont integration lifecycle"
```

### Task 5: Diagnostic sensors and redaction

**Files:**
- Create: `custom_components/longmont_utility/sensor.py`, `diagnostics.py`
- Create: `tests/test_sensor.py`, `tests/test_diagnostics.py`
- Modify: `custom_components/longmont_utility/__init__.py`, `strings.json`, `translations/en.json`

**Interfaces:**
- Consumes: coordinator fields `last_success: datetime | None`, `latest_interval: datetime | None`, and `last_error_category: str | None`.
- Produces: timestamp sensors for last successful update/latest interval, a duration sensor for data age, and `async_get_config_entry_diagnostics()` containing only public-safe health fields.

- [ ] **Step 1: Write failing entity and privacy tests**

Assert entity units/classes, unavailable behavior before first refresh, data-age calculation, and diagnostics redaction. Recursively scan serialized diagnostics and captured logs to prove test credentials, account refs, meter refs, addresses, session values, and export keys are absent.

- [ ] **Step 2: Run focused tests and confirm failure**

Run: `python -m pytest tests/test_sensor.py tests/test_diagnostics.py -q`

Expected: FAIL because sensor and diagnostics modules do not exist.

- [ ] **Step 3: Implement diagnostic entities and payload**

Use `SensorEntityDescription`, config-entry device grouping, UTC timestamps, and a derived duration in hours. Diagnostics include integration version, last-success timestamp, latest-interval timestamp, data age, and redacted error category only.

- [ ] **Step 4: Run all tests and checks**

Run: `python -m pytest tests -q && ruff check custom_components tests && mypy custom_components/longmont_utility`

Expected: all commands exit 0.

- [ ] **Step 5: Commit**

```bash
git add custom_components/longmont_utility tests
git commit -m "feat: expose Longmont import diagnostics"
```

### Task 6: Public documentation and validation workflows

**Files:**
- Create: `README.md`, `LICENSE`, `.github/workflows/validate.yml`, `.github/ISSUE_TEMPLATE/bug_report.yml`, `.github/ISSUE_TEMPLATE/config.yml`
- Modify: `PROJECT_LOG.md`, `manifest.json`, `hacs.json`
- Test: all repository validation commands

**Interfaces:**
- Consumes: final config flow, entities, statistic ID, and known limitations.
- Produces: documented HACS installation and CI validation for public release.

- [ ] **Step 1: Write documentation and release metadata**

Document HACS custom-repository installation, dedicated guest-account setup, Energy dashboard selection, one-day data latency, seven-day correction window, 90-day initial backfill, malformed-source handling, reauthentication, privacy, removal, and support boundaries. Use an OSI-approved MIT license and no real screenshots or identifiers.

- [ ] **Step 2: Add CI validation**

Create a workflow for supported Python that installs test dependencies and runs:

```bash
ruff check custom_components tests
mypy custom_components/longmont_utility
python -m pytest tests -q
```

Add official Hassfest and HACS validation actions pinned to immutable major-version tags accepted by their current documentation.

- [ ] **Step 3: Run a clean local validation pass**

Run: `ruff check custom_components tests && mypy custom_components/longmont_utility && python -m pytest tests -q`

Expected: all commands exit 0 with no warnings or skipped required tests.

- [ ] **Step 4: Inspect repository for private data**

Run targeted `rg` scans for the real email domain, account/address fragments, cookie names, token-like strings, and the downloaded CSV filename. Inspect every match; expected result is zero private-data matches.

- [ ] **Step 5: Update project history and commit**

Record implemented behavior, validation results, known limitations, and next release step in `PROJECT_LOG.md`.

```bash
git add README.md LICENSE .github hacs.json custom_components/longmont_utility/manifest.json PROJECT_LOG.md
git commit -m "docs: prepare public HACS release"
```

### Task 7: Final audit and public repository handoff

**Files:**
- Modify: any file required to resolve audit findings
- Modify: `PROJECT_LOG.md`

**Interfaces:**
- Consumes: the complete repository.
- Produces: one clean functionality/security audit pass and a releasable main branch.

- [ ] **Step 1: Run the mandatory full-audit workflow**

Review documentation, run every functional validation, remove dead code, audit dependencies and secret handling, and inspect Git history for private data. Fix each finding and repeat the entire audit until one pass reports zero functionality and zero security issues.

- [ ] **Step 2: Record the clean audit**

Append exact commands, versions, results, and the zero-issue conclusion to `PROJECT_LOG.md`.

- [ ] **Step 3: Commit the audit record**

```bash
git add -A
git commit -m "chore: record production readiness audit"
```

- [ ] **Step 4: Create and push the public repository**

After verifying the intended GitHub owner and repository visibility, create `ha-longmont-utility` as public, add it as `origin`, push `main`, and verify the public tree and Actions status contain no private data.
