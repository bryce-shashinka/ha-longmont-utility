from __future__ import annotations

import asyncio
from collections import deque
from datetime import date
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from custom_components.longmont_utility.client import (
    InvalidAuth,
    LongmontPortalClient,
    MeterInfo,
    PortalProtocolError,
)


class FakeResponse:
    def __init__(
        self,
        *,
        status: int = 200,
        text: str = "",
        body: bytes | None = None,
        url: str = "https://myutilityaccount.longmontcolorado.gov/app/capricorn",
        content_type: str = "text/html",
    ) -> None:
        self.status = status
        self._text = text
        self._body = body if body is not None else text.encode()
        self.url = url
        self.headers = {"Content-Type": content_type}

    async def text(self) -> str:
        return self._text

    async def read(self) -> bytes:
        return self._body

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = deque(responses)
        self.requests: list[tuple[str, str, dict[str, Any]]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.requests.append((method, url, kwargs))
        return self.responses.popleft()


LOGIN_HTML = """
<form method="post" action="/app/capricorn?para=index">
  <input type="hidden" name="jspCSRFToken" value="synthetic-csrf">
  <input name="accessCode">
  <input name="password" type="password">
  <input type="hidden" name="nextPara" value="">
</form>
"""

ACCOUNT_HTML = (
    '<a href="/app/capricorn?para=selectAccount&amp;userAction=refresh'
    '&amp;inAccountNumber=acct-test-1&amp;inMeterID=">Refresh</a>'
)

METER_HTML = """
<form name="hydroInquiry">
  <input type="hidden" name="selectedMeterId" value="meter-test-1">
</form>
"""


def synthetic_csv() -> str:
    values = ",".join(["0.125"] * 96)
    return f'"Reading Date","1 am kWh Usage"\r\n"2026-08-05",{values},"12.000",\r\n'


def test_authenticates_with_discovered_form_fields() -> None:
    session = FakeSession(
        [FakeResponse(text=LOGIN_HTML), FakeResponse(text=ACCOUNT_HTML)]
    )
    client = LongmontPortalClient(session, "person@example.invalid", "not-a-secret")

    asyncio.run(client.authenticate())

    assert session.requests[0][:2] == ("GET", "/app/login.jsp")
    method, url, kwargs = session.requests[1]
    assert (method, url) == ("POST", "/app/capricorn?para=index")
    assert kwargs["data"] == {
        "jspCSRFToken": "synthetic-csrf",
        "accessCode": "person@example.invalid",
        "password": "not-a-secret",
        "nextPara": "",
    }


def test_rejects_login_page_after_submit_without_leaking_credentials() -> None:
    session = FakeSession(
        [
            FakeResponse(text=LOGIN_HTML),
            FakeResponse(
                text=LOGIN_HTML,
                url="https://myutilityaccount.longmontcolorado.gov/app/login.jsp",
            ),
        ]
    )
    client = LongmontPortalClient(session, "person@example.invalid", "not-a-secret")

    with pytest.raises(InvalidAuth) as raised:
        asyncio.run(client.authenticate())

    assert "person@example.invalid" not in str(raised.value)
    assert "not-a-secret" not in str(raised.value)


def test_discovers_the_authorized_meter() -> None:
    session = FakeSession([FakeResponse(text=METER_HTML)])
    client = LongmontPortalClient(session, "person@example.invalid", "not-a-secret")
    client._account_page = ACCOUNT_HTML

    meters = asyncio.run(client.discover_meters())

    assert meters == (
        MeterInfo(
            account_ref="acct-test-1",
            meter_ref="meter-test-1",
            label="Longmont electric meter",
        ),
    )
    assert session.requests[0][:2] == (
        "GET",
        "/app/capricorn?para=smartMeterConsumV3&inquiryType=hydro&tab=SMCONSUM",
    )


def test_downloads_and_parses_the_two_stage_export() -> None:
    session = FakeSession(
        [
            FakeResponse(text=METER_HTML),
            FakeResponse(text="synthetic-export-key"),
            FakeResponse(
                body=synthetic_csv().encode(),
                content_type="text/csv;charset=UTF-8",
            ),
        ]
    )
    client = LongmontPortalClient(session, "person@example.invalid", "not-a-secret")
    meter = MeterInfo("acct-test-1", "meter-test-1", "Longmont electric meter")

    parsed = asyncio.run(
        client.download_usage(meter, date(2026, 8, 5), date(2026, 8, 5))
    )

    assert parsed[0].total_kwh == 12
    assert session.requests[0] == (
        "POST",
        "/app/index.jsp",
        {
            "data": {
                "para": "smartMeterConsumV3",
                "userAction": "refreshChart",
                "type": "daily",
                "inquiryType": "hydro",
                "dailyFromDate": "2026-08-05",
                "dailyToDate": "2026-08-05",
                "tab": "SMCONSUM",
                "selectedMeterId": "meter-test-1",
            }
        },
    )
    assert session.requests[-2][:2] == (
        "GET",
        "/app/capricorn?para=ajaxDownloadConsumptionData&type=smartmeterV3"
        "&inquiryType=hydro&isGenerationDataAvailable=false",
    )
    assert session.requests[-1][:2] == (
        "POST",
        "/app/ExcelExport?key=synthetic-export-key",
    )


def test_rejects_ranges_over_ninety_days() -> None:
    client = LongmontPortalClient(
        FakeSession([]), "person@example.invalid", "not-a-secret"
    )
    meter = MeterInfo("acct-test-1", "meter-test-1", "Longmont electric meter")

    with pytest.raises(PortalProtocolError, match="90 days"):
        asyncio.run(
            client.download_usage(meter, date(2026, 1, 1), date(2026, 4, 1))
        )


def test_protocol_errors_are_redacted() -> None:
    session = FakeSession([FakeResponse(text="<html>missing form</html>")])
    client = LongmontPortalClient(session, "person@example.invalid", "not-a-secret")

    with pytest.raises(PortalProtocolError) as raised:
        asyncio.run(client.authenticate())

    message = str(raised.value)
    assert "person@example.invalid" not in message
    assert "not-a-secret" not in message


def test_rejects_cross_origin_login_action() -> None:
    unsafe_form = LOGIN_HTML.replace(
        "/app/capricorn?para=index", "https://example.invalid/collect"
    )
    client = LongmontPortalClient(
        FakeSession([FakeResponse(text=unsafe_form)]),
        "person@example.invalid",
        "not-a-secret",
    )

    with pytest.raises(PortalProtocolError, match="login form changed"):
        asyncio.run(client.authenticate())


def test_retries_transient_portal_failures_at_most_three_times() -> None:
    session = FakeSession(
        [
            FakeResponse(status=503),
            FakeResponse(status=503),
            FakeResponse(text=LOGIN_HTML),
            FakeResponse(text=ACCOUNT_HTML),
        ]
    )
    client = LongmontPortalClient(session, "person@example.invalid", "not-a-secret")

    asyncio.run(client.authenticate())

    assert [request[:2] for request in session.requests[:3]] == [
        ("GET", "/app/login.jsp"),
        ("GET", "/app/login.jsp"),
        ("GET", "/app/login.jsp"),
    ]


def test_interval_timezone_is_longmont_local_time() -> None:
    session = FakeSession(
        [
            FakeResponse(text=METER_HTML),
            FakeResponse(text="synthetic-export-key"),
            FakeResponse(
                body=synthetic_csv().encode(),
                content_type="text/csv",
            ),
        ]
    )
    client = LongmontPortalClient(session, "person@example.invalid", "not-a-secret")
    meter = MeterInfo("acct-test-1", "meter-test-1", "Longmont electric meter")

    parsed = asyncio.run(
        client.download_usage(meter, date(2026, 8, 5), date(2026, 8, 5))
    )

    assert parsed[0].intervals[0].start.tzinfo == ZoneInfo("America/Denver")
