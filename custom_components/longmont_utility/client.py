"""Async client for the City of Longmont Cayenta utility portal."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from typing import Any, Protocol
from urllib.parse import parse_qs, quote, urlparse
from zoneinfo import ZoneInfo

from .const import PORTAL_TIME_ZONE
from .csv_parser import parse_smart_meter_csv
from .models import ParsedDay

LOGIN_PATH = "/app/login.jsp"
SMART_METER_PATH = (
    "/app/capricorn?para=smartMeterConsumV3&inquiryType=hydro&tab=SMCONSUM"
)
EXPORT_KEY_PATH = (
    "/app/capricorn?para=ajaxDownloadConsumptionData&type=smartmeterV3"
    "&inquiryType=hydro&isGenerationDataAvailable=false"
)


class PortalError(Exception):
    """Base class for redacted portal errors."""


class InvalidAuth(PortalError):
    """The portal rejected the configured credentials."""


class PortalProtocolError(PortalError):
    """The portal response did not match the supported contract."""


class PortalUnavailable(PortalError):
    """The portal could not complete a request."""


class _Response(Protocol):
    status: int
    url: object
    headers: dict[str, str]

    async def text(self) -> str: ...

    async def read(self) -> bytes: ...

    async def __aenter__(self) -> _Response: ...

    async def __aexit__(self, *args: object) -> None: ...


class _Session(Protocol):
    def request(self, method: str, url: str, **kwargs: Any) -> _Response: ...


@dataclass(frozen=True, slots=True)
class MeterInfo:
    """Opaque references for an electric meter authorized to the account."""

    account_ref: str
    meter_ref: str
    label: str


@dataclass(slots=True)
class _Form:
    action: str
    method: str
    fields: dict[str, str]


class _PortalHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.forms: list[_Form] = []
        self.refresh_hrefs: list[str] = []
        self._form: _Form | None = None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        values = dict(attrs)
        if tag == "form":
            self._form = _Form(
                action=values.get("action") or "",
                method=(values.get("method") or "get").upper(),
                fields={},
            )
            self.forms.append(self._form)
        elif tag == "input" and self._form is not None:
            name = values.get("name")
            if name:
                self._form.fields[name] = values.get("value") or ""
        elif tag == "a" and values.get("href"):
            href = values["href"]
            if href and "inAccountNumber=" in href:
                self.refresh_hrefs.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self._form = None


def _parse_html(payload: str) -> _PortalHtmlParser:
    parser = _PortalHtmlParser()
    parser.feed(payload)
    return parser


class LongmontPortalClient:
    """Operate one serialized authenticated Longmont portal session."""

    def __init__(self, session: _Session, username: str, password: str) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._lock = asyncio.Lock()
        self._account_page: str | None = None

    async def _text(self, method: str, path: str, **kwargs: Any) -> tuple[str, str]:
        for attempt in range(3):
            try:
                async with self._session.request(method, path, **kwargs) as response:
                    if response.status == 429 or response.status >= 500:
                        if attempt < 2:
                            await asyncio.sleep(0)
                            continue
                        raise PortalUnavailable("utility portal request failed")
                    if response.status >= 400:
                        raise PortalProtocolError("utility portal rejected a request")
                    return await response.text(), str(response.url)
            except PortalError:
                raise
            except Exception as err:
                raise PortalUnavailable("utility portal request failed") from err
        raise PortalUnavailable("utility portal request failed")

    async def authenticate(self) -> None:
        """Establish a portal session using the discovered login form."""

        async with self._lock:
            login_html, _ = await self._text("GET", LOGIN_PATH)
            forms = _parse_html(login_html).forms
            form = next(
                (
                    candidate
                    for candidate in forms
                    if "accessCode" in candidate.fields
                    and "password" in candidate.fields
                ),
                None,
            )
            if (
                form is None
                or form.method != "POST"
                or not form.action.startswith("/app/")
            ):
                raise PortalProtocolError("utility portal login form changed")
            data = dict(form.fields)
            data["accessCode"] = self._username
            data["password"] = self._password
            account_html, final_url = await self._text(
                "POST", form.action, data=data
            )
            if final_url.endswith("/app/login.jsp"):
                raise InvalidAuth("utility portal authentication failed")
            self._account_page = account_html

    async def discover_meters(self) -> tuple[MeterInfo, ...]:
        """Discover the single electric meter available to a v1 config entry."""

        async with self._lock:
            if self._account_page is None:
                raise PortalProtocolError("utility portal session is not authenticated")
            account_parser = _parse_html(self._account_page)
            if len(account_parser.refresh_hrefs) != 1:
                raise PortalProtocolError("expected one authorized utility account")
            query = parse_qs(urlparse(account_parser.refresh_hrefs[0]).query)
            account_refs = query.get("inAccountNumber", [])
            if len(account_refs) != 1 or not account_refs[0]:
                raise PortalProtocolError("authorized account reference is unavailable")
            meter_html, _ = await self._text("GET", SMART_METER_PATH)
            meter_forms = _parse_html(meter_html).forms
            meter_refs = [
                form.fields["selectedMeterId"]
                for form in meter_forms
                if form.fields.get("selectedMeterId")
            ]
            if len(meter_refs) != 1:
                raise PortalProtocolError("expected one authorized electric meter")
            return (
                MeterInfo(
                    account_ref=account_refs[0],
                    meter_ref=meter_refs[0],
                    label="Longmont electric meter",
                ),
            )

    async def download_usage(
        self,
        meter: MeterInfo,
        start: date,
        end: date,
    ) -> tuple[ParsedDay, ...]:
        """Download and normalize a daily export of quarter-hour readings."""

        if end < start or (end - start).days >= 90:
            raise PortalProtocolError("usage range must be between 1 and 90 days")
        async with self._lock:
            await self._text(
                "POST",
                "/app/index.jsp",
                data={
                    "para": "smartMeterConsumV3",
                    "userAction": "refreshChart",
                    "type": "daily",
                    "inquiryType": "hydro",
                    "dailyFromDate": start.isoformat(),
                    "dailyToDate": end.isoformat(),
                    "tab": "SMCONSUM",
                    "selectedMeterId": meter.meter_ref,
                },
            )
            export_key, _ = await self._text("GET", EXPORT_KEY_PATH)
            export_key = export_key.strip()
            if not export_key:
                raise PortalProtocolError("utility portal returned no export key")
            path = f"/app/ExcelExport?key={quote(export_key, safe='')}"
            try:
                async with self._session.request("POST", path) as response:
                    if response.status != 200:
                        raise PortalProtocolError("utility export request failed")
                    content_type = response.headers.get("Content-Type", "").lower()
                    if "csv" not in content_type:
                        raise PortalProtocolError("utility export was not CSV")
                    payload = (await response.read()).decode("utf-8-sig")
            except PortalError:
                raise
            except Exception as err:
                raise PortalUnavailable("utility export request failed") from err
            return parse_smart_meter_csv(payload, ZoneInfo(PORTAL_TIME_ZONE))
