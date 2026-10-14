"""Daily scrape of the City's published residential (RE) electric rates.

The City publishes RE prices only as an HTML table. Each day the coordinator
fetches the page, strictly validates the table, and records a new dated
``RateSchedule`` whenever the published values differ from the newest schedule
already known (built-in or previously observed). Fetch or parse failures never
interrupt the usage import; costs keep using the last known rates.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from itertools import pairwise
from typing import Any, Protocol

from .tariff import RE_SCHEDULES, RateSchedule, Tier

_LOGGER = logging.getLogger(__name__)

RATES_URL = (
    "https://longmontcolorado.gov/longmont-power-communications/"
    "rates-and-fees/residential-rates/"
)
RATES_STORE_VERSION = 1
FAILURES_BEFORE_REPAIR = 7

MIN_PRICE = Decimal("0.03")
MAX_PRICE = Decimal("0.60")
MAX_CUSTOMER_CHARGE = Decimal(100)

_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|"
    "November|December"
)
_EFFECTIVE = re.compile(
    r"\beffective(?:\s+(?:on|as\s+of|beginning|starting|from))?\s*:?\s*"
    rf"(?:(?P<month>{_MONTHS})\.?\s+(?P<day>\d{{1,2}}),?\s+(?P<year>\d{{4}})"
    r"|(?P<m>\d{1,2})/(?P<d>\d{1,2})/(?P<y>\d{4}))",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


class RateParseError(Exception):
    """The published rate table was missing or failed validation."""


class _TableParser(HTMLParser):
    """Collect every table as rows of whitespace-normalized cell text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self.text: list[str] = []
        self._depth = 0
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._depth += 1
            if self._depth == 1:
                self.tables.append([])
        elif tag == "tr" and self._depth == 1:
            self.tables[-1].append([])
        elif tag in {"td", "th"} and self._depth == 1 and self.tables[-1]:
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "table":
            self._depth = max(0, self._depth - 1)
        elif tag in {"td", "th"} and self._cell is not None:
            self.tables[-1][-1].append(" ".join("".join(self._cell).split()))
            self._cell = None

    def handle_data(self, data: str) -> None:
        self.text.append(data)
        if self._cell is not None:
            self._cell.append(data)


def _cents(text: str) -> Decimal:
    match = _NUMBER.search(text)
    if match is None or "¢" not in text:
        raise RateParseError("price cell is not in cents")
    return Decimal(match.group().replace(",", "")) / 100


def _dollars(text: str) -> Decimal:
    match = _NUMBER.search(text)
    if match is None or "$" not in text:
        raise RateParseError("customer charge cell is not in dollars")
    return Decimal(match.group().replace(",", ""))


def _effective_date(page_text: str) -> date | None:
    match = _EFFECTIVE.search(page_text)
    if match is None:
        return None
    try:
        if match.group("month"):
            return datetime.strptime(
                f"{match.group('month')} {match.group('day')} {match.group('year')}",
                "%B %d %Y",
            ).date()
        return date(int(match.group("y")), int(match.group("m")), int(match.group("d")))
    except ValueError:
        return None


def _find_re_table(tables: list[list[list[str]]]) -> list[list[str]]:
    for table in tables:
        if not table:
            continue
        header = [cell.lower() for cell in table[0]]
        if (
            len(header) >= 5
            and "tier" in header[0]
            and "non-summer" in header[2]
            and "summer" in header[3]
            and "customer charge" in header[4]
        ):
            return table[1:]
    raise RateParseError("residential tier table not found")


def validate_schedule(schedule: RateSchedule) -> None:
    """Reject anything that does not look like a three-tier RE schedule."""

    tiers = schedule.tiers
    if len(tiers) != 3:
        raise RateParseError("expected exactly three tiers")
    limits = [tier.limit_kwh for tier in tiers]
    if limits[-1] is not None or any(limit is None for limit in limits[:-1]):
        raise RateParseError("only the last tier may be unbounded")
    bounded = [limit for limit in limits[:-1] if limit is not None]
    if any(b <= a for a, b in pairwise([Decimal(0), *bounded])):
        raise RateParseError("tier boundaries must increase")
    for season in ("non_summer", "summer"):
        prices = [getattr(tier, season) for tier in tiers]
        if any(b <= a for a, b in pairwise(prices)):
            raise RateParseError("tier prices must increase")
    for tier in tiers:
        if tier.summer < tier.non_summer:
            raise RateParseError("summer price below non-summer price")
        for price in (tier.summer, tier.non_summer):
            if not MIN_PRICE <= price <= MAX_PRICE:
                raise RateParseError("price outside plausible range")
    if not Decimal(0) <= schedule.customer_charge <= MAX_CUSTOMER_CHARGE:
        raise RateParseError("customer charge outside plausible range")


def parse_residential_rates(
    html: str, *, first_seen: date
) -> tuple[RateSchedule, bool]:
    """Parse and validate the RE table.

    Returns the schedule and whether its effective date was stated on the page
    (otherwise ``first_seen`` is used).
    """

    parser = _TableParser()
    parser.feed(html)
    rows = _find_re_table(parser.tables)
    tiers: list[Tier] = []
    charges: set[Decimal] = set()
    try:
        for index, row in enumerate(rows):
            if len(row) < 5:
                raise RateParseError("short tier row")
            usage = row[1]
            if index == len(rows) - 1:
                if not re.search(r"more|over|above|\+", usage, re.IGNORECASE):
                    raise RateParseError("last tier is not open-ended")
                limit = None
            else:
                numbers = _NUMBER.findall(usage)
                if not numbers:
                    raise RateParseError("tier boundary missing")
                limit = Decimal(numbers[-1].replace(",", ""))
            tiers.append(Tier(limit, _cents(row[2]), _cents(row[3])))
            charges.add(_dollars(row[4]))
    except InvalidOperation as err:
        raise RateParseError("unreadable number") from err
    if len(charges) != 1:
        raise RateParseError("customer charge differs between tiers")
    stated = _effective_date(" ".join(" ".join(parser.text).split()))
    schedule = RateSchedule(
        effective=stated or first_seen,
        customer_charge=charges.pop(),
        tiers=tuple(tiers),
    )
    validate_schedule(schedule)
    return schedule, stated is not None


def same_prices(left: RateSchedule, right: RateSchedule) -> bool:
    """Compare everything except the effective date."""

    return left.customer_charge == right.customer_charge and left.tiers == right.tiers


def schedule_to_dict(schedule: RateSchedule) -> dict[str, Any]:
    """Serialize a schedule for the private rates store."""

    return {
        "effective_date": schedule.effective.isoformat(),
        "customer_charge": str(schedule.customer_charge),
        "tiers": [
            {
                "limit_kwh": None if tier.limit_kwh is None else str(tier.limit_kwh),
                "non_summer": str(tier.non_summer),
                "summer": str(tier.summer),
            }
            for tier in schedule.tiers
        ],
    }


def schedule_from_dict(data: dict[str, Any]) -> RateSchedule:
    """Restore a stored schedule."""

    return RateSchedule(
        effective=date.fromisoformat(data["effective_date"]),
        customer_charge=Decimal(data["customer_charge"]),
        tiers=tuple(
            Tier(
                None if tier["limit_kwh"] is None else Decimal(tier["limit_kwh"]),
                Decimal(tier["non_summer"]),
                Decimal(tier["summer"]),
            )
            for tier in data["tiers"]
        ),
    )


class StorageBackend(Protocol):
    """Subset of Home Assistant Store used by the rate tracker."""

    async def async_load(self) -> dict[str, Any] | None: ...

    async def async_save(self, data: dict[str, Any]) -> None: ...


@dataclass(frozen=True, slots=True)
class RateCheck:
    """Outcome of one daily check."""

    attempted: bool
    changed: RateSchedule | None = None
    error: str | None = None


class RateTracker:
    """Merge built-in schedules with daily-observed published rates."""

    def __init__(
        self,
        store: StorageBackend,
        fetch: Callable[[], Awaitable[str]],
        *,
        builtin: tuple[RateSchedule, ...] = RE_SCHEDULES,
    ) -> None:
        self._store = store
        self._fetch = fetch
        self._builtin = builtin
        self._observed: list[RateSchedule] = []
        self._last_attempt: date | None = None
        self._last_checked: datetime | None = None
        self._failures = 0
        self._loaded = False

    async def async_load(self) -> None:
        """Load observations once."""

        if self._loaded:
            return
        data = await self._store.async_load() or {}
        self._observed = [
            schedule_from_dict(item) for item in data.get("observations", [])
        ]
        attempt = data.get("last_attempt")
        self._last_attempt = date.fromisoformat(attempt) if attempt else None
        checked = data.get("last_checked")
        self._last_checked = datetime.fromisoformat(checked) if checked else None
        self._failures = int(data.get("consecutive_failures", 0))
        self._loaded = True

    async def _async_save(self) -> None:
        await self._store.async_save(
            {
                "observations": [schedule_to_dict(item) for item in self._observed],
                "last_attempt": (
                    self._last_attempt.isoformat() if self._last_attempt else None
                ),
                "last_checked": (
                    self._last_checked.isoformat() if self._last_checked else None
                ),
                "consecutive_failures": self._failures,
            }
        )

    @property
    def schedules(self) -> tuple[RateSchedule, ...]:
        """Built-in schedules followed by observations (later wins on ties)."""

        return (*self._builtin, *self._observed)

    @property
    def latest(self) -> RateSchedule:
        """Return the newest-effective known schedule."""

        newest = self.schedules[0]
        for schedule in self.schedules:
            if schedule.effective >= newest.effective:
                newest = schedule
        return newest

    @property
    def source(self) -> str:
        """Whether the newest schedule came from the code or the City page."""

        return "scraped" if self.latest in self._observed else "built-in"

    @property
    def last_checked(self) -> datetime | None:
        """Last time the page was read and validated successfully."""

        return self._last_checked

    @property
    def consecutive_failures(self) -> int:
        """Daily attempts that failed since the last success."""

        return self._failures

    async def async_check(self, today: date, now: datetime) -> RateCheck:
        """Check the published rates at most once per local day."""

        await self.async_load()
        if self._last_attempt == today:
            return RateCheck(attempted=False)
        self._last_attempt = today
        try:
            html = await self._fetch()
            observed, _ = parse_residential_rates(html, first_seen=today)
        except Exception as err:
            self._failures += 1
            await self._async_save()
            _LOGGER.warning(
                "Could not read Longmont residential rates (%s failures): %s",
                self._failures,
                type(err).__name__,
            )
            return RateCheck(attempted=True, error=type(err).__name__)
        self._failures = 0
        self._last_checked = now
        changed: RateSchedule | None = None
        if not same_prices(observed, self.latest):
            self._observed.append(observed)
            changed = observed
            _LOGGER.info(
                "Longmont residential rates changed; effective %s", observed.effective
            )
        await self._async_save()
        return RateCheck(attempted=True, changed=changed)
