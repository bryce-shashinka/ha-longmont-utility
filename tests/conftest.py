from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from datetime import date
from decimal import Decimal

import pytest


@pytest.fixture
def csv_payload_factory():
    def build(
        rows: Iterable[tuple[date, Iterable[str | Decimal], str | Decimal]],
        *,
        line_ending: str = "\n",
        trailing_empty: bool = True,
    ) -> str:
        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator=line_ending)
        writer.writerow(
            ["Reading Date"]
            + [f"{hour} kWh Usage" for hour in range(1, 25)]
            + ["Total"]
        )
        for reading_date, intervals, total in rows:
            row: list[object] = [reading_date.isoformat(), *intervals, total]
            if trailing_empty:
                row.append("")
            writer.writerow(row)
        return output.getvalue()

    return build

